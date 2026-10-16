from asyncio import create_task, sleep, to_thread
from os import path as ospath
from time import time
from uuid import uuid4

from aiofiles import open as aiopen
from aiofiles.os import makedirs as aiomakedirs
from niquests import AsyncSession
from pyrogram.enums import ParseMode

from .. import DOWNLOAD_DIR, LOGGER
from ..helper.ext_utils.bot_utils import new_task
from ..helper.ext_utils.files_utils import clean_download, clean_target
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)

try:
    from PIL import Image
except ImportError:
    Image = None
    LOGGER.error("Overlap: Pillow is not installed")

OVER_STORE = {}
EXPIRY_TASKS = set()
STORE_TTL = 600
MAX_BYTES = 15 * 1024 * 1024
BASE_DIR = ospath.join(DOWNLOAD_DIR, "overlap")

NON_IMAGE_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/javascript",
    "video/",
    "audio/",
)

POS_MAP = {
    "tl": ("left", "top"),
    "t": ("center", "top"),
    "tr": ("right", "top"),
    "ml": ("left", "center"),
    "c": ("center", "center"),
    "mr": ("right", "center"),
    "bl": ("left", "bottom"),
    "b": ("center", "bottom"),
    "br": ("right", "bottom"),
}

POS_NAME = {
    "tl": "Top Left",
    "t": "Top",
    "tr": "Top Right",
    "ml": "Middle Left",
    "c": "Center",
    "mr": "Middle Right",
    "bl": "Bottom Left",
    "b": "Bottom",
    "br": "Bottom Right",
}

POS_BUTTONS = [
    ("↖ Top Left", "tl"),
    ("🔼 Top", "t"),
    ("↗ Top Right", "tr"),
    ("◀ Middle Left", "ml"),
    ("🎯 Center", "c"),
    ("▶ Middle Right", "mr"),
    ("↙ Bottom Left", "bl"),
    ("🔽 Bottom", "b"),
    ("↘ Bottom Right", "br"),
]


async def release(uid):
    entry = OVER_STORE.pop(uid, None)
    if entry:
        await clean_download(entry["dir"])


async def expire(uid):
    await sleep(STORE_TTL)
    await release(uid)


def schedule_expiry(uid):
    task = create_task(expire(uid))
    EXPIRY_TASKS.add(task)
    task.add_done_callback(EXPIRY_TASKS.discard)


def place_coords(pw, ph, lw, lh, pos):
    xs = {"left": 0, "center": (pw - lw) // 2, "right": pw - lw}
    ys = {"top": 0, "center": (ph - lh) // 2, "bottom": ph - lh}
    return xs[pos[0]], ys[pos[1]]


def normalize_image(src, dst):
    with Image.open(src) as im:
        im.convert("RGBA").save(dst, "PNG")


def merge_images(poster_path, logo_path, scale_percent, pos_key, out_path):
    poster = Image.open(poster_path).convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    pw, ph = poster.size
    target_w = max(1, pw * scale_percent // 100)
    target_h = max(1, int(logo.size[1] * target_w / logo.size[0]))
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    x, y = place_coords(
        pw, ph, logo.size[0], logo.size[1], POS_MAP.get(pos_key, POS_MAP["c"])
    )

    base = poster.copy()
    base.alpha_composite(logo, dest=(max(0, x), max(0, y)))
    base.convert("RGB").save(out_path, format="JPEG", quality=95)
    return out_path


async def download(client, uid, label, url, file_path):
    tmp_path = f"{file_path}_tmp"
    try:
        response = await client.get(url, timeout=20, allow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if content_type.startswith(NON_IMAGE_TYPES):
            LOGGER.warning(
                f"Overlap [{uid}] {label} is not an image ({content_type}): {url}"
            )
            return False

        content = response.content
        if len(content) > MAX_BYTES:
            LOGGER.warning(
                f"Overlap [{uid}] {label} too large ({len(content)} bytes): {url}"
            )
            return False

        async with aiopen(tmp_path, "wb") as f:
            await f.write(content)

        await to_thread(normalize_image, tmp_path, file_path)
        return True
    except Exception as e:
        LOGGER.error(f"Overlap [{uid}] {label} failed for {url}: {e}")
        return False
    finally:
        await clean_target(tmp_path)


def build_buttons(uid, user_id):
    buttons = ButtonMaker()
    for label, key in POS_BUTTONS:
        buttons.data_button(label, f"ov {user_id} pos {uid} {key}")
    buttons.data_button("🗑️ Remove", f"ov {user_id} rem {uid}", "footer")
    return buttons.build_menu(3)


@new_task
async def overlap(_, message):
    if Image is None:
        return await send_message(message, "Pillow is not installed.")

    args = message.command
    if len(args) < 3:
        return await send_message(
            message,
            "<b>Format:</b>\n"
            "<code>/overlap {poster_url} {logo_url} [scale_percent]</code>",
        )

    poster_url, logo_url = args[1], args[2]

    scale = 20
    if len(args) >= 4:
        try:
            scale = int(args[3])
        except ValueError:
            scale = 20
    scale = min(max(scale, 1), 100)

    uid = uuid4().hex[:12]
    user_id = message.from_user.id
    status = await send_message(message, "<i>Downloading images...</i>")

    folder = ospath.join(BASE_DIR, uid)
    try:
        await aiomakedirs(folder, exist_ok=True)
    except Exception as e:
        LOGGER.error(f"Overlap [{uid}] could not create {folder}: {e}")
        return await edit_message(status, "<b>Failed to prepare workspace.</b>")

    poster_path = ospath.join(folder, "poster.png")
    logo_path = ospath.join(folder, "logo.png")

    async with AsyncSession() as client:
        poster_ok = await download(client, uid, "poster", poster_url, poster_path)
        logo_ok = await download(client, uid, "logo", logo_url, logo_path)

    if not poster_ok or not logo_ok:
        await clean_download(folder)
        return await edit_message(
            status,
            "<b>Failed to download one or both images.</b>\n"
            "Use direct image links (png, jpg, webp).",
        )

    OVER_STORE[uid] = {
        "dir": folder,
        "poster": poster_path,
        "logo": logo_path,
        "scale": scale,
        "user_id": user_id,
        "time": time(),
    }
    schedule_expiry(uid)

    await edit_message(
        status,
        f"🥂 <b>Overlay:</b> None | <b>Scale:</b> {scale}%",
        build_buttons(uid, user_id),
    )


@new_task
async def overlap_cb(client, query):
    data = query.data.split()
    if len(data) < 4:
        return await query.answer()

    message = query.message
    user_id = query.from_user.id

    try:
        owner_id = int(data[1])
    except ValueError:
        return await query.answer()

    if user_id != owner_id:
        return await query.answer("Not Yours!", show_alert=True)

    action, uid = data[2], data[3]

    if action == "rem":
        await release(uid)
        await query.answer("Removed")
        return await delete_message(message, message.reply_to_message)

    if action != "pos":
        return await query.answer()

    entry = OVER_STORE.get(uid)
    if not entry:
        await query.answer("Expired", show_alert=True)
        return await edit_message(message, "<b>Session expired.</b>")

    pos = data[4] if len(data) >= 5 else "c"

    await query.answer("Processing..")
    await edit_message(message, "<i>Processing...</i>")

    try:
        out_path = ospath.join(entry["dir"], "overlap.jpg")
        await to_thread(
            merge_images,
            entry["poster"],
            entry["logo"],
            entry["scale"],
            pos,
            out_path,
        )
        caption = (
            f"🥂 <b>Overlay:</b> {POS_NAME.get(pos, 'Center')} | "
            f"<b>Scale:</b> {entry['scale']}%"
        )
        await client.send_photo(
            message.chat.id,
            out_path,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=(
                message.reply_to_message.id if message.reply_to_message else None
            ),
        )
        LOGGER.info(f"Overlap [{uid}] sent to chat {message.chat.id} (user {user_id})")
        await release(uid)
        await delete_message(message)
    except Exception as e:
        LOGGER.error(f"Overlap [{uid}] processing failed: {e}", exc_info=True)
        await release(uid)
        await edit_message(message, "<b>Failed to process image.</b>")
