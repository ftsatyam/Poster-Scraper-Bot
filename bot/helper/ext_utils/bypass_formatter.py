from html import escape


DOWNLOAD_KINDS = {"download", "torrent", "magnet", "subtitle", "other"}
STREAM_KINDS = {"stream"}


def _text(value):
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _display_label(resource):
    label = _text(resource.get("label")) or _text(resource.get("provider")) or "Link"
    quality = _text(resource.get("quality"))
    if quality and quality.casefold() not in label.casefold():
        return f"{label} ({quality})"
    return label


def _resource_url(resource):
    url = resource.get("url")
    return url.strip() if isinstance(url, str) and url.strip() else None


def _unique_resources(resources):
    output = []
    seen = set()
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        url = _resource_url(resource)
        if not url or url in seen:
            continue
        seen.add(url)
        output.append(resource)
    return output


def _items(payload):
    items = payload.get("items")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _media(payload):
    media = payload.get("media")
    if not isinstance(media, list):
        return []
    return _unique_resources(media)


def _item_name(item, title, index):
    return _text(item.get("name")) or title or f"File {index}"


def _item_size(item, resources):
    size = _text(item.get("size"))
    if size:
        return size
    for resource in resources:
        size = _text(resource.get("size"))
        if size:
            return size
    return None


def _legacy_resource(value, default_label):
    if isinstance(value, str):
        return {"kind": "download", "label": default_label, "url": value}
    if not isinstance(value, dict):
        return None
    link = value.get("url") or value.get("link") or value.get("direct_link")
    if not isinstance(link, str) or not link.strip():
        return None
    return {
        "kind": "stream" if value.get("type") in {"stream", "player"} else "download",
        "label": value.get("label") or value.get("provider") or value.get("type") or default_label,
        "url": link,
        "size": value.get("size") or value.get("file_size") or value.get("filesize"),
        "quality": value.get("quality"),
    }


def _legacy_payload(data):
    resources = []
    for key in ("links", "downloads", "download_links", "direct_links", "streaming_urls", "streams", "players"):
        values = data.get(key)
        if not isinstance(values, list):
            values = [values] if values not in (None, "") else []
        for value in values:
            resource = _legacy_resource(value, key.replace("_", " ").title())
            if resource:
                resources.append(resource)
    direct_link = data.get("direct_link")
    if direct_link:
        resource = _legacy_resource(direct_link, "Direct Link")
        if resource:
            resources.append(resource)
    media = []
    for key in ("images", "image_links", "screenshots", "posters", "logos"):
        values = data.get(key)
        if not isinstance(values, list):
            values = [values] if values not in (None, "") else []
        for value in values:
            resource = _legacy_resource(value, key.replace("_", " ").title())
            if resource:
                resource["kind"] = "image"
                media.append(resource)
    item = {
        "name": data.get("filename") or data.get("file_name") or data.get("title"),
        "size": data.get("size") or data.get("file_size") or data.get("filesize"),
        "resources": resources,
    }
    return {
        "title": data.get("title"),
        "media": media,
        "items": [item] if resources or item["name"] or item["size"] else [],
    }


def _payload(data):
    payload = data.get("data") if isinstance(data.get("data"), dict) else None
    if payload is not None and any(key in payload for key in ("items", "media", "title", "description", "thumbnail")):
        return payload
    return _legacy_payload(data)


def _link_line(resource):
    label = escape(_display_label(resource))
    url = escape(_resource_url(resource), quote=True)
    return f"• {label} ➙ <a href=\"{url}\">CLICK HERE</a>"


def format_bypass_result(data: dict, url: str) -> str:
    payload = _payload(data)
    title = _text(payload.get("title"))
    items = _items(payload)
    lines = []

    for index, item in enumerate(items, 1):
        resources = _unique_resources(item.get("resources", []))
        name = escape(_item_name(item, title, index))
        size = _item_size(item, resources)
        lines.append(f"<b>Name :</b> {name}")
        if size:
            lines.append(f"<b>Size :</b> {escape(size)}")

        downloads = [
            resource
            for resource in resources
            if resource.get("kind") in DOWNLOAD_KINDS
        ]
        streams = [
            resource
            for resource in resources
            if resource.get("kind") in STREAM_KINDS
        ]
        other = [
            resource
            for resource in resources
            if resource.get("kind") not in DOWNLOAD_KINDS | STREAM_KINDS
        ]

        if downloads:
            lines.extend(["", "<b>• Direct Link •</b>"])
            lines.extend(_link_line(resource) for resource in downloads)
        if streams:
            lines.extend(["", "<b>• Watch Online •</b>"])
            lines.extend(_link_line(resource) for resource in streams)
        if other:
            lines.extend(["", "<b>• More Links •</b>"])
            lines.extend(_link_line(resource) for resource in other)
        lines.append("")

    media = _media(payload)
    if media:
        if lines and lines[-1] == "":
            lines.pop()
        lines.extend(["", "<b>• Thumbnails / Images / Posters / Logos •</b>"])
        for index, resource in enumerate(media, 1):
            media_url = escape(_resource_url(resource), quote=True)
            lines.append(f'{index}. <a href="{media_url}">Click Here</a>')

    if not lines:
        lines.append("<code>No links found.</code>")

    source_url = escape(url, quote=True)
    lines.extend(["", "<b>⚜ Original URL</b>", f'<a href="{source_url}">Click Here</a>'])
    return "\n".join(lines)
