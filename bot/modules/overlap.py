from asyncio import to_thread
from io import BytesIO
from time import time
from uuid import uuid4

from niquests import AsyncSession
from pyrogram.enums import ParseMode

from .. import LOGGER
from ..helper.ext_utils.bot_utils import new_task
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

OVER_STORE = {}
STORE_TTL = 600
MAX_BYTES = 15 * 1024 * 1024

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


def clean_store():
    now = time()
    for key in [k for k, v in OVER_STORE.items() if now - v["time"] > STORE_TTL]:
        OVER_STORE.pop(key, None)


def place_coords(pw, ph, lw, lh, pos):
    xs = {"left": 0, "center": (pw - lw) // 2, "right": pw - lw}
    ys = {"top": 0, "center": (ph - lh) // 2, "bottom": ph - lh}
    return xs[pos[0]], ys[pos[1]]


def merge_images(poster_bytes, logo_bytes, scale_percent, pos_key):
    poster = Image.open(BytesIO(poster_bytes)).convert("RGBA")
    logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")

    pw, ph = poster.size
    target_w = max(1, pw * scale_percent // 100)
    target_h = max(1, int(logo.size[1] * target_w / logo.size[0]))
    logo = logo.resize((target_w, target_h), Image.LANCZOS)

    x, y = place_coords(
        pw, ph, logo.size[0], logo.size[1], POS_MAP.get(pos_key, POS_MAP["c"])
    )

    base = poster.copy()
    base.alpha_composite(logo, dest=(max(0, x), max(0, y)))

    out = BytesIO()
    base.convert("RGB").save(out, format="JPEG", quality=95)
    out.seek(0)
    out.name = "overlap.jpg"
    return out


async def download(client, url):
    try:
        response = await client.get(url, timeout=20)
        response.raise_for_status()
        content = response.content
        if len(content) > MAX_BYTES:
            return None
        return content
    except Exception as e:
        LOGGER.error(f"Overlap download failed: {e}")
        return None


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

    clean_store()

    status = await send_message(message, "<i>Downloading images...</i>")

    async with AsyncSession() as client:
        poster_bytes = await download(client, poster_url)
        logo_bytes = await download(client, logo_url)

    if not poster_bytes or not logo_bytes:
        return await edit_message(
            status, "<b>Failed to download one or both images.</b>"
        )

    uid = uuid4().hex[:12]
    user_id = message.from_user.id

    OVER_STORE[uid] = {
        "poster": poster_bytes,
        "logo": logo_bytes,
        "scale": scale,
        "user_id": user_id,
        "time": time(),
    }

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

    if user_id != int(data[1]):
        return await query.answer("Not Yours!", show_alert=True)

    action, uid = data[2], data[3]

    if action == "rem":
        OVER_STORE.pop(uid, None)
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
        out = await to_thread(
            merge_images, entry["poster"], entry["logo"], entry["scale"], pos
        )
        caption = (
            f"🥂 <b>Overlay:</b> {POS_NAME.get(pos, 'Center')} | "
            f"<b>Scale:</b> {entry['scale']}%"
        )
        await client.send_photo(
            message.chat.id,
            out,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=(
                message.reply_to_message.id if message.reply_to_message else None
            ),
        )
        OVER_STORE.pop(uid, None)
        await delete_message(message)
    except Exception as e:
        LOGGER.error(f"Overlap merge failed: {e}")
        await edit_message(message, "<b>Failed to process image.</b>")
