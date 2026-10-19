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


def test_normalized_links_render_as_clickable_telegram_anchors():
    source = "https://source.example/share/abc"
    result = format_bypass_result(
        {
            "success": True,
            "platform": "source.example",
            "url": source,
            "direct_link": "https://cdn.example/one.mkv",
            "links": [
                {
                    "label": "1080p",
                    "type": "download",
                    "url": "https://cdn.example/one.mkv",
                    "file_name": "movie.mkv",
                    "file_size": "1.4GB",
                },
                {
                    "label": "Telegram",
                    "type": "download",
                    "url": "https://t.me/example/2",
                },
            ],
            "title": "A <sample> title",
            "file_name": "movie.mkv",
            "file_size": "1.4GB",
            "data": {"provider_specific": "not shown as JSON"},
            "credits": {"developer": "Example"},
        },
        source,
    )

    assert "<b>✺ Direct Links:</b>" in result
    assert '<a href="https://cdn.example/one.mkv">Click Here</a>' in result
    assert '<a href="https://t.me/example/2">Click Here</a>' in result
    assert "1080p — movie.mkv — 1.4GB" in result
    assert "A &lt;sample&gt; title" in result
    assert "provider_specific" not in result
    assert "credits" not in result


def test_legacy_single_direct_link_still_formats():
    result = format_bypass_result(
        {"url": "https://source.example/abc", "direct_link": "https://cdn.example/file"},
        "https://source.example/abc",
    )

    assert "<b>✺ Direct Link:</b>" in result
    assert '<a href="https://cdn.example/file">Click Here</a>' in result


def test_missing_link_reports_no_direct_link():
    result = format_bypass_result({"success": True, "links": []}, "https://source.example/abc")

    assert "No direct link found." in result
