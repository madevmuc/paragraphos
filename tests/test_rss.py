from pathlib import Path

import httpx
import pytest
import respx

from core.rss import FeedHealth, build_manifest, build_manifest_with_url

FIX = Path(__file__).parent / "fixtures" / "sample_feed.xml"


@respx.mock
def test_build_manifest_parses_items():
    respx.get("https://a.test/rss").respond(200, text=FIX.read_text())
    episodes = build_manifest("https://a.test/rss")
    assert len(episodes) == 2
    first = episodes[0]
    for key in ("guid", "title", "pubDate", "duration",
                "episode_number", "mp3_url", "description", "url"):
        assert key in first
    assert first["mp3_url"].startswith("https://")
    assert first["episode_number"].isdigit()


def test_build_manifest_rejects_non_http():
    with pytest.raises(Exception):
        build_manifest("file:///etc/passwd")


@respx.mock
def test_feed_health_ok_on_200():
    respx.head("https://ok.test/rss").respond(200)
    h = FeedHealth.check("https://ok.test/rss")
    assert h.ok is True


@respx.mock
def test_feed_health_reports_failure_on_4xx():
    respx.head("https://dead.test/rss").respond(404)
    h = FeedHealth.check("https://dead.test/rss")
    assert h.ok is False
    assert "404" in h.reason


@respx.mock
def test_build_manifest_with_url_returns_canonical_after_redirect():
    """Feed 301-redirects; build_manifest_with_url exposes the final URL
    so the caller can persist it in watchlist.yaml."""
    respx.get("https://old.test/rss").respond(
        301, headers={"location": "https://new.test/rss"})
    respx.get("https://new.test/rss").respond(200, text=FIX.read_text())
    canonical, episodes = build_manifest_with_url("https://old.test/rss")
    assert canonical == "https://new.test/rss"
    assert len(episodes) == 2


@respx.mock
def test_build_manifest_with_url_same_url_when_no_redirect():
    respx.get("https://stable.test/rss").respond(200, text=FIX.read_text())
    canonical, _ = build_manifest_with_url("https://stable.test/rss")
    assert canonical == "https://stable.test/rss"
