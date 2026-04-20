from pathlib import Path

import pytest
import respx

from core.scrape import scrape_episode

FIX = Path(__file__).parent / "fixtures"


@respx.mock
def test_scrape_og_audio():
    respx.head("https://example.com/ep42").respond(200, headers={"content-type": "text/html"})
    respx.get("https://example.com/ep42").respond(
        200, text=(FIX / "podigee_episode.html").read_text(),
    )
    ep = scrape_episode("https://example.com/ep42")
    assert ep.mp3_url == "https://cdn.podigee.com/ep-42.mp3"
    assert ep.title == "Folge 42: Mietspiegel"
    assert ep.show_name == "Immocation"
    assert ep.pub_date == "2026-04-15"


@respx.mock
def test_scrape_jsonld():
    respx.head("https://example.com/j").respond(200, headers={"content-type": "text/html"})
    respx.get("https://example.com/j").respond(
        200, text=(FIX / "jsonld_episode.html").read_text(),
    )
    ep = scrape_episode("https://example.com/j")
    assert ep.mp3_url == "https://example.com/audio.mp3"
    assert ep.title == "Example Episode"
    assert ep.show_name == "Example Show"
    assert ep.pub_date == "2026-03-01"


@respx.mock
def test_scrape_direct_mp3():
    respx.head("https://x.test/a.mp3").respond(
        200, headers={"content-type": "audio/mpeg", "content-length": "1000"},
    )
    ep = scrape_episode("https://x.test/a.mp3")
    assert ep.mp3_url == "https://x.test/a.mp3"
    assert ep.title == "a"


@respx.mock
def test_scrape_fail_raises():
    respx.head("https://empty.test/").respond(200, headers={"content-type": "text/html"})
    respx.get("https://empty.test/").respond(200, text="<html></html>")
    with pytest.raises(ValueError):
        scrape_episode("https://empty.test/")
