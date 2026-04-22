"""Per-channel YouTube transcript-source override in Show Details dialog.

Verifies:
- For YouTube shows, a "Transcript source" combo is constructed and
  (after expanding the Advanced section) visible.
- For podcast shows, the combo is either absent or hidden.
- Changing the combo updates `Show.youtube_transcript_pref` (persisted
  on Save like the other Advanced fields).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from core.models import Settings, Show, Watchlist
from core.state import StateStore
from ui.app_context import AppContext

_app_ref = QApplication.instance() or QApplication([])
_keepalive: list = []


@pytest.fixture
def qapp():
    return _app_ref


def _make_ctx(tmp_path, show: Show) -> AppContext:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    settings.output_root = str(tmp_path / "out")
    watchlist = Watchlist(shows=[show])
    watchlist.save(data_dir / "watchlist.yaml")
    state = StateStore(data_dir / "state.sqlite")
    state.init_schema()
    return AppContext(
        data_dir=data_dir,
        settings=settings,
        watchlist=watchlist,
        state=state,
        library=None,  # type: ignore[arg-type]
    )


def _make_dialog(show: Show, tmp_path):
    from ui.show_details_dialog import ShowDetailsDialog

    ctx = _make_ctx(tmp_path, show)
    dlg = ShowDetailsDialog(ctx, show.slug)
    _keepalive.append(dlg)
    return dlg


def test_youtube_show_has_transcript_pref_combo(qapp, tmp_path):
    show = Show(
        slug="ch",
        title="Channel",
        rss="https://ytfeed",
        source="youtube",
        youtube_transcript_pref="captions",
    )
    dlg = _make_dialog(show, tmp_path)
    combo = getattr(dlg, "transcript_pref_combo", None)
    assert combo is not None
    # Combo lives inside the Advanced section which is collapsed by
    # default — pop it open and show the dialog so visibility checks pass.
    dlg.show()
    dlg._advanced_switch.setChecked(True)
    qapp.processEvents()
    assert combo.isVisible()
    dlg.hide()


def test_podcast_show_has_no_transcript_pref_combo(qapp, tmp_path):
    show = Show(slug="p", title="P", rss="https://feed", source="podcast")
    dlg = _make_dialog(show, tmp_path)
    combo = getattr(dlg, "transcript_pref_combo", None)
    if combo is not None:
        # Even with Advanced expanded, podcast shows should not show it.
        dlg.show()
        dlg._advanced_switch.setChecked(True)
        qapp.processEvents()
        assert not combo.isVisible()
        dlg.hide()


def test_combo_updates_show_field_on_save(qapp, tmp_path):
    show = Show(
        slug="ch",
        title="Channel",
        rss="https://ytfeed",
        source="youtube",
    )
    dlg = _make_dialog(show, tmp_path)
    combo = dlg.transcript_pref_combo
    assert combo is not None
    # Index 1 = "Always whisper" per the wiring in the dialog.
    combo.setCurrentIndex(1)
    qapp.processEvents()
    dlg._save()
    assert show.youtube_transcript_pref == "whisper"


def test_combo_default_when_pref_empty(qapp, tmp_path):
    show = Show(
        slug="ch",
        title="Channel",
        rss="https://ytfeed",
        source="youtube",
    )
    dlg = _make_dialog(show, tmp_path)
    combo = dlg.transcript_pref_combo
    assert combo is not None
    # Empty pref should select "captions" (first option) by default.
    assert combo.currentData() == "captions"
