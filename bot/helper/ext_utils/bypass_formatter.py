from html import escape
from json import dumps

SKIP_FIELDS = {
    "url",
    "direct_link",
    "links",
    "data",
    "headers",
    "credits",
    "success",
}


def format_label(key: str) -> str:
    return str(key).replace("_", " ").strip().title()


def format_value(value) -> str:
    if isinstance(value, (dict, list)):
        value = dumps(value, ensure_ascii=False)
    return escape(str(value))


def _as_link_items(data):
    raw_links = data.get("links")
    if isinstance(raw_links, dict):
        raw_links = [
            {"label": label, "url": link}
            for label, link in raw_links.items()
            if isinstance(link, str)
        ]
    elif isinstance(raw_links, str):
        raw_links = [{"label": "Direct link", "url": raw_links}]
    elif not isinstance(raw_links, list):
        raw_links = []

    items = []
    seen = set()
    for item in raw_links:
        if isinstance(item, str):
            item = {"label": "Direct link", "url": item}
        if not isinstance(item, dict):
            continue
        link = item.get("url") or item.get("link") or item.get("direct_link")
        if not isinstance(link, str) or not link or link in seen:
            continue
        seen.add(link)
        items.append(
            {
                "label": item.get("label") or item.get("type") or f"Link {len(items) + 1}",
                "url": link,
                "file_name": item.get("file_name") or item.get("filename"),
                "file_size": item.get("file_size") or item.get("filesize") or item.get("size"),
            }
        )

    if not items:
        direct_link = data.get("direct_link")
        if isinstance(direct_link, str) and direct_link:
            items.append({"label": "Direct link", "url": direct_link})
        elif isinstance(direct_link, dict):
            link = direct_link.get("url") or direct_link.get("link")
            if isinstance(link, str) and link:
                items.append({"label": direct_link.get("label") or "Direct link", "url": link})
    return items


def format_bypass_result(data: dict, url: str) -> str:
    items = _as_link_items(data)
    heading = "<b>✺ Direct Link:</b>" if len(items) == 1 else "<b>✺ Direct Links:</b>"
    lines = [heading]

    if items:
        for item in items:
            label = str(item.get("label") or "Link")
            detail_parts = [label]
            file_name = item.get("file_name")
            file_size = item.get("file_size")
            if file_name and str(file_name).casefold() != label.casefold():
                detail_parts.append(str(file_name))
            if file_size:
                detail_parts.append(str(file_size))
            caption = " — ".join(detail_parts)
            lines.append(
                f'<b>{escape(caption)}</b>: '
                f'<a href="{escape(item["url"], quote=True)}">Click Here</a>'
            )
    else:
        lines.append("<code>No direct link found.</code>")

    details = []
    for key, value in data.items():
        if key in SKIP_FIELDS or value in (None, ""):
            continue
        details.append(f"<b>{format_label(key)}:</b> {format_value(value)}")

    if details:
        lines.extend(["", *details])

    lines.extend(["", "<b>✺ Original URL:</b>", f"<code>{escape(url)}</code>"])
    return "\n".join(lines)
