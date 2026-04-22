import json
from unittest.mock import MagicMock, patch

from core.youtube_meta import (
    YoutubeMetaError,
    enumerate_channel_videos,
    fetch_channel_preview,
    resolve_handle_to_channel_id,
)


def _setup_fake_ytdlp(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)


def test_resolve_handle_uses_http_fast_path(monkeypatch):
    """Happy path: scrape the @handle page for the canonical channel URL."""
    fake_html = (
        "<html><head>"
        '<link rel="canonical" href="https://www.youtube.com/channel/UCabc1234567890123456789">'
        "</head></html>"
    )
    monkeypatch.setattr("core.youtube_meta._http_get_text", lambda url, timeout=10.0: fake_html)
    cid = resolve_handle_to_channel_id("MrBeast")
    assert cid == "UCabc1234567890123456789"


def test_resolve_handle_falls_back_to_ytdlp_when_http_fails(tmp_path, monkeypatch):
    """If the HTTP scrape fails or returns no canonical link, fall back to yt-dlp."""
    _setup_fake_ytdlp(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "core.youtube_meta._http_get_text",
        lambda url, timeout=10.0: (_ for _ in ()).throw(RuntimeError("network down")),
    )
    fake_proc = MagicMock(returncode=0, stdout=json.dumps({"channel_id": "UCabc"}), stderr="")
    with patch("subprocess.run", return_value=fake_proc) as run:
        cid = resolve_handle_to_channel_id("MrBeast")
        assert cid == "UCabc"
        args = run.call_args[0][0]
        assert "https://www.youtube.com/@MrBeast" in args


def test_enumerate_channel_videos_parses_flat_playlist(tmp_path, monkeypatch):
    _setup_fake_ytdlp(tmp_path, monkeypatch)
    output = "\n".join(
        [
            json.dumps({"id": "vid1", "title": "First", "timestamp": 1700000000}),
            json.dumps({"id": "vid2", "title": "Second", "timestamp": 1700001000}),
        ]
    )
    fake_proc = MagicMock(returncode=0, stdout=output, stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        vids = enumerate_channel_videos("UCabc")
        assert [v["id"] for v in vids] == ["vid1", "vid2"]
        assert vids[0]["title"] == "First"


def test_default_timeouts_are_generous():
    """Smoke: each public meta call must allow at least 90s for yt-dlp."""
    import inspect

    import core.youtube_meta as ym

    src = inspect.getsource(ym)
    # Bumped per-call timeouts: 120/180/300.
    assert "timeout=120" in src
    assert "timeout=180" in src
    assert "timeout=300" in src


def test_fetch_channel_preview_uses_rss_fast_path(monkeypatch):
    """Happy path: read the channel's hidden RSS feed (no yt-dlp)."""
    rss = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>Mr Beast</title>"
        "<entry><title>vid 1</title></entry>"
        "<entry><title>vid 2</title></entry>"
        "</feed>"
    )
    monkeypatch.setattr("core.youtube_meta._http_get_text", lambda url, timeout=10.0: rss)
    prev = fetch_channel_preview("UCabc")
    assert prev["title"] == "Mr Beast"
    assert prev["video_count"] == 2
    assert prev["video_count_is_lower_bound"] is True


def test_fetch_channel_preview_falls_back_to_ytdlp(tmp_path, monkeypatch):
    """If the RSS scrape fails, fall back to yt-dlp for the exact count."""
    _setup_fake_ytdlp(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "core.youtube_meta._http_get_text",
        lambda url, timeout=10.0: (_ for _ in ()).throw(RuntimeError("network down")),
    )
    payload = {
        "channel_id": "UCabc",
        "channel": "Mr Beast",
        "playlist_count": 700,
        "thumbnails": [{"url": "https://yt3/.../mqdefault.jpg", "width": 320}],
    }
    fake_proc = MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        prev = fetch_channel_preview("UCabc")
        assert prev["title"] == "Mr Beast"
        assert prev["video_count"] == 700
        assert prev["artwork_url"].startswith("https://")
        assert prev["video_count_is_lower_bound"] is False
