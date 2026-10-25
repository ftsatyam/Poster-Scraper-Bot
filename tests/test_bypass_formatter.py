import importlib.util
from pathlib import Path


FORMATTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "bot"
    / "helper"
    / "ext_utils"
    / "bypass_formatter.py"
)
_spec = importlib.util.spec_from_file_location("bypass_formatter", FORMATTER_PATH)
_formatter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_formatter)
format_bypass_result = _formatter.format_bypass_result


SOURCE = "https://source.example/movie"


def canonical_response():
    return {
        "success": True,
        "service": "hdhub4u",
        "provider": "hubcloud",
        "source_url": SOURCE,
        "data": {
            "title": "Example Movie",
            "description": "Not shown in the bypass message",
            "thumbnail": "https://cdn.example/poster.jpg",
            "media": [
                {
                    "kind": "poster",
                    "label": "Poster",
                    "url": "https://cdn.example/poster.jpg",
                },
                {
                    "kind": "image",
                    "label": "Screenshot",
                    "url": "https://cdn.example/screenshot.jpg",
                },
            ],
            "items": [
                {
                    "name": "Example.Movie.1080p.mkv",
                    "size": "2 GB",
                    "resources": [
                        {
                            "kind": "download",
                            "label": "HubCloud",
                            "url": "https://cdn.example/movie.mkv",
                            "provider": "hubcloud",
                            "quality": "1080p",
                        },
                        {
                            "kind": "download",
                            "label": "Instant DL",
                            "url": "https://cdn.example/movie.mkv?instant=1",
                            "provider": "instant",
                        },
                        {
                            "kind": "stream",
                            "label": "Watch Online",
                            "url": "https://player.example/movie",
                            "provider": "player",
                        },
                    ],
                }
            ],
        },
        "credits": {"developer": "The Zake"},
    }


def test_canonical_response_uses_name_size_and_resource_sections():
    result = format_bypass_result(canonical_response(), SOURCE)

    assert "<b>Name :</b> Example.Movie.1080p.mkv" in result
    assert "<b>Size :</b> 2 GB" in result
    assert "<b>• Direct Link •</b>" in result
    assert "HubCloud (1080p)" in result
    assert "Instant DL" in result
    assert '<a href="https://cdn.example/movie.mkv">CLICK HERE</a>' in result
    assert "<b>• Watch Online •</b>" in result
    assert '<a href="https://player.example/movie">CLICK HERE</a>' in result


def test_canonical_media_are_numbered_and_original_url_is_clickable():
    result = format_bypass_result(canonical_response(), SOURCE)

    assert "<b>• Thumbnails / Images / Posters / Logos •</b>" in result
    assert '1. <a href="https://cdn.example/poster.jpg">Click Here</a>' in result
    assert '2. <a href="https://cdn.example/screenshot.jpg">Click Here</a>' in result
    assert f'<a href="{SOURCE}">Click Here</a>' in result


def test_canonical_values_are_escaped_for_telegram_html():
    response = canonical_response()
    response["data"]["items"][0]["name"] = "Movie <1080p> & Sample"
    result = format_bypass_result(response, "https://source.example/a?x=1&y=2")

    assert "Movie &lt;1080p&gt; &amp; Sample" in result
    assert "source.example/a?x=1&amp;y=2" in result


def test_empty_canonical_items_report_no_links_and_keep_original_url():
    result = format_bypass_result(
        {
            "success": True,
            "service": "gofile",
            "source_url": SOURCE,
            "data": {"title": "Empty", "media": [], "items": []},
            "credits": {},
        },
        SOURCE,
    )

    assert "No links found." in result
    assert f'<a href="{SOURCE}">Click Here</a>' in result


def test_legacy_poster_api_payload_is_rendered_in_the_same_layout():
    result = format_bypass_result(
        {
            "title": "Legacy Movie",
            "file_name": "legacy.mkv",
            "file_size": "700 MB",
            "links": [
                {"label": "Instant DL", "url": "https://cdn.example/legacy.mkv"},
                {"label": "Watch", "type": "stream", "url": "https://player.example/legacy"},
            ],
        },
        SOURCE,
    )

    assert "<b>Name :</b> legacy.mkv" in result
    assert "<b>Size :</b> 700 MB" in result
    assert "Instant DL" in result
    assert "<b>• Watch Online •</b>" in result
