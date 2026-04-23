"""Tests for ui.worker_thread._pctx_for — YouTube wiring."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.models import Settings, Show
from ui.worker_thread import CheckAllThread

_app_ref = QApplication.instance() or QApplication([])


def _make_thread(tmp_path, settings: Settings | None = None) -> CheckAllThread:
    settings = settings or Settings()
    ctx = SimpleNamespace(
        state=object(),
        library=object(),
        data_dir=tmp_path,
        watchlist=SimpleNamespace(shows=[]),
    )
    return CheckAllThread(ctx, settings)


def test_pctx_for_youtube_show_populates_channel_id(tmp_path):
    cid = "UCabc1234567890123456789"
    settings = Settings(sources_youtube=True, youtube_default_transcript_source="captions")
    th = _make_thread(tmp_path, settings)
    show = Show(
        slug="mr-beast",
        title="Mr Beast",
        rss=f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
        source="youtube",
        youtube_transcript_pref="whisper",
    )
    pctx = th._pctx_for(show)
    assert pctx.source == "youtube"
    assert pctx.youtube_channel_id == cid
    assert pctx.youtube_transcript_pref == "whisper"
    assert pctx.youtube_default_transcript_source == "captions"


def test_pctx_for_youtube_show_inherits_default_transcript_source(tmp_path):
    cid = "UCxyz9876543210987654321"
    settings = Settings(youtube_default_transcript_source="whisper")
    th = _make_thread(tmp_path, settings)
    show = Show(
        slug="x",
        title="X",
        rss=f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
        source="youtube",
    )
    pctx = th._pctx_for(show)
    assert pctx.youtube_channel_id == cid
    assert pctx.youtube_transcript_pref == ""
    assert pctx.youtube_default_transcript_source == "whisper"


def test_pctx_for_podcast_show_omits_youtube_fields(tmp_path):
    th = _make_thread(tmp_path)
    show = Show(slug="p", title="P", rss="https://example.com/feed.rss")
    pctx = th._pctx_for(show)
    assert pctx.source == "podcast"
    assert pctx.youtube_channel_id == ""
