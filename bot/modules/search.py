from asyncio import to_thread
from html import escape
from time import time
from uuid import uuid4

from pyrogram.enums import ButtonStyle
from simplejustwatchapi import search as jw_search

from .. import LOGGER
from ..helper.ext_utils.bot_utils import new_task
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.message_utils import (
    edit_message,
    edit_reply_markup,
    send_message,
)

DEFAULT_REGION = "IN"
CACHE = {}
CACHE_TTL = 6 * 3600
CACHE_MAX = 200
STORE = {}
STORE_TTL = 3600
STORE_MAX = 500
MAX_TITLES = 7
MAX_LEN = 3600
ORDER = ("Stream", "Free", "Rent", "Buy")
ICONS = {"Stream": "◈", "Free": "✦", "Rent": "❖", "Buy": "✧"}
TYPE_ICONS = {"MOVIE": "▣", "SHOW": "▦"}
KINDS = {
    "FLATRATE": "Stream",
    "ADS": "Free",
    "FREE": "Free",
    "RENT": "Rent",
    "BUY": "Buy",
}


def monetization(value):
    name = str(getattr(value, "name", value)).upper()
    return KINDS.get(name.rsplit(".", 1)[-1])


def fetch(query, region):
    results = jw_search(query, country=region, language="en", count=10)
    data = []
    for item in results:
        offers = []
        for offer in item.offers or []:
            kind = monetization(offer.monetization_type)
            url = getattr(offer, "url", None)
            if kind and url:
                offers.append((kind, offer.package.name, url))
        if offers:
            data.append(
                {
                    "title": item.title,
                    "year": item.release_year,
                    "type": str(item.object_type).upper(),
                    "offers": offers,
                }
            )
    return data


async def get_results(query, region):
    key = (query.lower(), region)
    cached = CACHE.get(key)
    if cached and time() - cached[0] < CACHE_TTL:
        return cached[1]

    data = await to_thread(fetch, query, region)

    if len(CACHE) >= CACHE_MAX:
        CACHE.pop(next(iter(CACHE)), None)
    CACHE[key] = (time(), data)
    return data


def format_title(entry, expanded):
    grouped = {}
    seen = set()
    for kind, name, url in entry["offers"]:
        if (kind, name) in seen:
            continue
        seen.add((kind, name))
        grouped.setdefault(kind, []).append(
            f'• {escape(name)}: <a href="{escape(url, quote=True)}">Watch Here</a>'
        )

    icon = TYPE_ICONS["MOVIE"] if "MOVIE" in entry["type"] else TYPE_ICONS["SHOW"]
    year = f" ({entry['year']})" if entry["year"] else ""
    head = f"<b>{icon} {escape(entry['title'])}</b>{year}"

    body = []
    for kind in ORDER:
        if kind in grouped:
            body.append(f"<b>{ICONS[kind]} {kind}:</b>")
            body.extend(grouped[kind])
    text = "\n".join(body)

    if expanded:
        return f"{head}\n{text}"
    return f"{head}\n<blockquote expandable>{text}</blockquote>"


def build_pages(data):
    pages = []
    current = []
    total = 0
    for entry in data:
        size = len(format_title(entry, True))
        if current and (len(current) >= MAX_TITLES or total + size > MAX_LEN):
            pages.append(current)
            current = []
            total = 0
        current.append(entry)
        total += size
    if current:
        pages.append(current)
    return pages


def build_text(session, page):
    pages = session["pages"]
    blocks = [format_title(e, i == 0) for i, e in enumerate(pages[page])]

    header = (
        f"<b>✺ Search:</b> {escape(session['query'])}\n"
        f"<b>✺ Region:</b> {session['region']}\n"
        f"<b>✺ Results:</b> {session['count']}\n"
    )
    if len(pages) > 1:
        header += f"<b>✺ Page:</b> {page + 1}/{len(pages)}\n"

    return (
        header
        + "\n"
        + "\n\n".join(blocks)
        + "\n\n<blockquote>Data by JustWatch | Bot By ➤ @TheZake</blockquote>"
    )


def build_buttons(user_id, uid, page, total):
    buttons = ButtonMaker()
    if total > 1:
        if page > 0:
            buttons.data_button("◀ Prev", f"sr {user_id} {uid} {page - 1}", "header")
        buttons.data_button(f"{page + 1}/{total}", f"sr {user_id} {uid} noop", "header")
        if page < total - 1:
            buttons.data_button("Next ▶", f"sr {user_id} {uid} {page + 1}", "header")
    buttons.url_button("Developer", "https://t.me/TheZake", style=ButtonStyle.PRIMARY)
    buttons.url_button(
        "⭐ Source Code",
        "https://github.com/ImKrishana/Poster-Scraper-Bot",
        style=ButtonStyle.SUCCESS,
    )
    return buttons.build_menu(2, 3)


def clean_store():
    now = time()
    for key in [k for k, v in STORE.items() if now - v["time"] > STORE_TTL]:
        STORE.pop(key, None)
    while len(STORE) >= STORE_MAX:
        STORE.pop(next(iter(STORE)), None)


@new_task
async def search(_, message):
    args = message.command[1:]
    region = DEFAULT_REGION
    if len(args) > 1 and len(args[-1]) == 2 and args[-1].isalpha():
        region = args[-1].upper()
        args = args[:-1]

    query = " ".join(args).strip()
    if not query:
        return await send_message(
            message,
            "<b>Format:</b>\n"
            "<code>/search dune</code>\n"
            "<code>/search dune US</code>",
        )

    waiting = await send_message(
        message, f"<i>Searching for:</i> <code>{escape(query)}</code>"
    )

    try:
        data = await get_results(query, region)
    except Exception as e:
        LOGGER.error(f"Search [{query}/{region}] failed: {e}", exc_info=True)
        return await edit_message(
            waiting, "<b>Error:</b> <code>Could not fetch platforms right now.</code>"
        )

    if not data:
        return await edit_message(
            waiting,
            f"<b>No platforms found</b> for <code>{escape(query)}</code> "
            f"in <b>{region}</b>.",
        )

    clean_store()
    uid = uuid4().hex[:12]
    user_id = message.from_user.id
    session = {
        "query": query,
        "region": region,
        "pages": build_pages(data),
        "count": len(data),
        "user_id": user_id,
        "time": time(),
    }
    STORE[uid] = session

    await edit_message(
        waiting,
        build_text(session, 0),
        build_buttons(user_id, uid, 0, len(session["pages"])),
    )


@new_task
async def search_cb(_, query):
    data = query.data.split()
    if len(data) < 4:
        return await query.answer()

    message = query.message

    try:
        owner_id = int(data[1])
    except ValueError:
        return await query.answer()

    if query.from_user.id != owner_id:
        return await query.answer("Not Yours!", show_alert=True)

    uid, action = data[2], data[3]
    if action == "noop":
        return await query.answer()

    session = STORE.get(uid)
    if not session or time() - session["time"] > STORE_TTL:
        STORE.pop(uid, None)
        await query.answer("Expired, search again.", show_alert=True)
        return await edit_reply_markup(message, build_buttons(owner_id, uid, 0, 1))

    try:
        page = int(action)
    except ValueError:
        return await query.answer()

    total = len(session["pages"])
    page = min(max(page, 0), total - 1)

    await query.answer()
    await edit_message(
        message,
        build_text(session, page),
        build_buttons(owner_id, uid, page, total),
    )
