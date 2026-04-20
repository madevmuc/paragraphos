from pathlib import Path

from core.opml import parse_opml


def test_parse_opml_returns_shows():
    shows = parse_opml(Path(__file__).parent / "fixtures" / "sample.opml")
    assert len(shows) == 2
    titles = {s["title"] for s in shows}
    assert titles == {"Immocation", "1 A Lage"}
    assert all(s["xmlUrl"].startswith("http") for s in shows)
