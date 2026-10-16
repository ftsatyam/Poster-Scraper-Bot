from asyncio import to_thread
from html import escape
from time import time

from pyrogram.enums import ButtonStyle
from simplejustwatchapi import search as jw_search

from .. import LOGGER
from ..helper.ext_utils.bot_utils import new_task
from ..helper.telegram_helper.button_build import ButtonMaker
from ..helper.telegram_helper.message_utils import edit_message, send_message

DEFAULT_REGION = "IN"
CACHE = {}
CACHE_TTL = 6 * 3600
CACHE_MAX = 200
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


def build_text(query, region, data):
    blocks = []
    total = 0
    for index, entry in enumerate(data[:MAX_TITLES]):
        block = format_title(entry, index == 0)
        if blocks and total + len(block) > MAX_LEN:
            break
        blocks.append(block)
        total += len(block)

    header = (
        f"<b>✺ Search:</b> {escape(query)}\n"
        f"<b>✺ Region:</b> {region}\n"
        f"<b>✺ Results:</b> {len(blocks)} of {len(data)}\n\n"
    )
    return (
        header
        + "\n\n".join(blocks)
        + "\n\n<blockquote>Bot By ➤ @TheZake</blockquote>"
    )


def build_buttons():
    buttons = ButtonMaker()
    buttons.url_button(
        "Developer", "https://t.me/TheZake", style=ButtonStyle.PRIMARY
    )
    buttons.url_button(
        "⭐ Source Code",
        "https://github.com/ImKrishana/Poster-Scraper-Bot",
        style=ButtonStyle.SUCCESS,
    )
    return buttons.build_menu(2)


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

    await edit_message(waiting, build_text(query, region, data), build_buttons())
