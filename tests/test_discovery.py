import json
from pathlib import Path

import httpx
import pytest
import respx

from core.discovery import (
    PodcastMatch, find_rss_from_url, resolve_input, search_itunes,
)

FIX = Path(__file__).parent / "fixtures"


@respx.mock
def test_search_itunes_returns_matches():
    respx.get("https://itunes.apple.com/search").respond(
        200, json=json.loads((FIX / "itunes_immocation.json").read_text()),
    )
    matches = search_itunes("immocation")
    assert len(matches) >= 1
    assert all(isinstance(m, PodcastMatch) for m in matches)
    assert matches[0].feed_url.startswith("http")


@respx.mock
def test_search_itunes_empty():
    respx.get("https://itunes.apple.com/search").respond(
        200, json={"resultCount": 0, "results": []},
    )
    assert search_itunes("zzz") == []


@respx.mock
def test_search_itunes_http_error():
    respx.get("https://itunes.apple.com/search").respond(500)
    with pytest.raises(httpx.HTTPStatusError):
        search_itunes("x")


@respx.mock
def test_find_rss_link_alternate():
    respx.get("https://example.com/").respond(
        200, text=(FIX / "landing_with_rss.html").read_text(),
    )
    assert find_rss_from_url("https://example.com/") == "https://example.com/feed/mp3"


@respx.mock
def test_direct_rss_url_passes_through():
    respx.get("https://example.com/feed").respond(
        200, text="<?xml version='1.0'?><rss><channel/></rss>",
        headers={"content-type": "application/rss+xml"},
    )
    assert find_rss_from_url("https://example.com/feed") == "https://example.com/feed"


@respx.mock
def test_resolve_input_url():
    respx.get("https://example.com/").respond(
        200, text=(FIX / "landing_with_rss.html").read_text(),
    )
    assert resolve_input("https://example.com/") == "https://example.com/feed/mp3"


def test_resolve_input_non_url_raises():
    with pytest.raises(ValueError):
        resolve_input("not a url")
