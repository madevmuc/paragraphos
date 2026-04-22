"""Tests for the YouTube URL mode in AddShowDialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.models import Settings

_app_ref = QApplication.instance() or QApplication([])
_keepalive: list = []


def _make_dialog(tmp_path, settings: Settings):
    from ui.add_show_dialog import AddShowDialog
    from ui.app_context import AppContext

    ctx = AppContext.load(tmp_path)
    ctx.settings = settings
    dlg = AddShowDialog(ctx, None)
    _keepalive.append(dlg)
    return dlg


def _yt_mode_present(dlg) -> bool:
    return any(b.property("mode") == "youtube" for b in dlg._mode_buttons.buttons())


def test_youtube_mode_visible_when_setting_on(tmp_path):
    dlg = _make_dialog(tmp_path, Settings(sources_youtube=True))
    assert _yt_mode_present(dlg)
    assert hasattr(dlg, "youtube_url_input")


def test_youtube_mode_hidden_when_setting_off(tmp_path):
    dlg = _make_dialog(tmp_path, Settings(sources_youtube=False))
    assert not _yt_mode_present(dlg)


def test_paste_channel_url_triggers_preview_fetch(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr(
        "core.youtube_meta.fetch_channel_preview",
        lambda cid: (
            called.update(cid=cid),
            {
                "channel_id": cid,
                "title": "Mr Beast",
                "video_count": 700,
                "artwork_url": "",
            },
        )[1],
    )
    dlg = _make_dialog(tmp_path, Settings(sources_youtube=True))
    dlg._activate_youtube_mode()
    dlg.youtube_url_input.setText("https://www.youtube.com/channel/UCabc1234567890123456789")
    dlg._on_youtube_url_resolve()
    # Resolution runs synchronously in the test entrypoint.
    assert called.get("cid") == "UCabc1234567890123456789"
    assert dlg._loaded_yt_preview["title"] == "Mr Beast"


def test_handle_url_resolves_then_previews(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr(
        "core.youtube_meta.resolve_handle_to_channel_id",
        lambda h: "UCabc1234567890123456789",
    )
    seen = {}
    monkeypatch.setattr(
        "core.youtube_meta.fetch_channel_preview",
        lambda cid: (
            seen.update(cid=cid),
            {"channel_id": cid, "title": "T", "video_count": 1, "artwork_url": ""},
        )[1],
    )
    dlg = _make_dialog(tmp_path, Settings(sources_youtube=True))
    dlg._activate_youtube_mode()
    dlg.youtube_url_input.setText("https://www.youtube.com/@somehandle")
    dlg._on_youtube_url_resolve()
    assert seen.get("cid") == "UCabc1234567890123456789"


def test_add_yt_channel_persists_show(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    cid = "UCabc1234567890123456789"
    monkeypatch.setattr(
        "core.youtube_meta.fetch_channel_preview",
        lambda c: {
            "channel_id": cid,
            "title": "Mr Beast",
            "video_count": 700,
            "artwork_url": "https://example.com/cover.jpg",
        },
    )
    monkeypatch.setattr(
        "core.youtube_meta.enumerate_channel_videos",
        lambda c, limit=None: [],
    )
    dlg = _make_dialog(tmp_path, Settings(sources_youtube=True))
    dlg._activate_youtube_mode()
    dlg.youtube_url_input.setText(f"https://www.youtube.com/channel/{cid}")
    dlg._on_youtube_url_resolve()
    # Bypass the modal accept() — call _do_save directly via the YT add path.
    dlg._add_from_youtube()
    shows = dlg.updated_watchlist.shows
    assert any(s.source == "youtube" and s.slug == "mr-beast" for s in shows)
    yt = next(s for s in shows if s.source == "youtube")
    assert yt.rss == f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    assert yt.artwork_url == "https://example.com/cover.jpg"


def test_install_gate_when_ytdlp_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: False)
    dlg = _make_dialog(tmp_path, Settings(sources_youtube=True))
    dlg._activate_youtube_mode()
    # The install button is shown; resolve is gated.
    assert not dlg._yt_install_btn.isHidden()
    assert not dlg.youtube_url_input.isEnabled()
