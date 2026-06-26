"""Show Details → full episode browser (Tasks 4.1 + 4.2).

4.1 — the recent-episodes table grows into a full browser: every episode
     for the show renders (the old ``LIMIT 10`` is gone) and the window is
     resizable/maximizable.
4.2 — the table supports row multi-select while keeping the per-row guid
     stash + context-menu resolution intact; ``_selected_guids`` returns the
     guids of all selected rows.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTableWidget

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


def _seed_episodes(ctx: AppContext, slug: str, n: int) -> list[str]:
    """Seed ``n`` episodes with descending pub_dates; return guids in
    pub_date-DESC order (newest first) so they match the table's row order."""
    guids: list[str] = []
    for i in range(n):
        guid = f"{slug}-ep{i:02d}"
        # pub_dates ascending with i so DESC order reverses the seed order.
        ctx.state.upsert_episode(
            show_slug=slug,
            guid=guid,
            title=f"Episode {i}",
            pub_date=f"2026-06-{i + 1:02d}T00:00:00+00:00",
            mp3_url=f"https://example.com/{guid}.mp3",
        )
        guids.append(guid)
    # Newest first == highest pub_date first == reversed seed order.
    return list(reversed(guids))


def _make_dialog(show: Show, tmp_path):
    from ui.show_details_dialog import ShowDetailsDialog

    ctx = _make_ctx(tmp_path, show)
    dlg = ShowDetailsDialog(ctx, show.slug)
    _keepalive.append(dlg)
    return dlg


# ── Task 4.1 ─────────────────────────────────────────────────────────────


def test_all_episodes_render_no_limit(qapp, tmp_path):
    """15 seeded episodes → all 15 rows render (the LIMIT 10 is gone)."""
    show = Show(slug="full", title="Full", rss="https://feed", source="podcast")
    from ui.show_details_dialog import ShowDetailsDialog

    ctx = _make_ctx(tmp_path, show)
    _seed_episodes(ctx, "full", 15)
    dlg = ShowDetailsDialog(ctx, "full")
    _keepalive.append(dlg)
    assert dlg._episodes_tbl.rowCount() == 15


def test_window_is_resizable_maximizable(qapp, tmp_path):
    """The dialog keeps a minimum size but is not fixed, and the maximize
    button hint is enabled so the browser can grow to fill the screen."""
    show = Show(slug="rz", title="Rz", rss="https://feed", source="podcast")
    dlg = _make_dialog(show, tmp_path)
    # Not fixed: max size is the Qt 'unbounded' sentinel, not the min.
    assert dlg.maximumWidth() > dlg.minimumWidth()
    assert bool(dlg.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)


# ── Task 4.2 ─────────────────────────────────────────────────────────────


def test_table_is_row_multiselect(qapp, tmp_path):
    show = Show(slug="ms", title="Ms", rss="https://feed", source="podcast")
    dlg = _make_dialog(show, tmp_path)
    tbl = dlg._episodes_tbl
    assert tbl.selectionMode() == QTableWidget.SelectionMode.ExtendedSelection
    assert tbl.selectionBehavior() == QTableWidget.SelectionBehavior.SelectRows


def test_selected_guids_returns_selected_rows(qapp, tmp_path):
    show = Show(slug="sel", title="Sel", rss="https://feed", source="podcast")
    from ui.show_details_dialog import ShowDetailsDialog

    ctx = _make_ctx(tmp_path, show)
    guids = _seed_episodes(ctx, "sel", 5)
    dlg = ShowDetailsDialog(ctx, "sel")
    _keepalive.append(dlg)

    tbl = dlg._episodes_tbl
    tbl.clearSelection()
    tbl.selectRow(0)
    # Extend the selection to row 2 without clearing row 0.
    tbl.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
    tbl.selectRow(2)
    tbl.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

    assert set(dlg._selected_guids()) == {guids[0], guids[2]}


def test_per_row_guid_stash_survives_refactor(qapp, tmp_path):
    """The Date cell still carries its guid at UserRole after the
    multi-select refactor (the context menu relies on it)."""
    show = Show(slug="stash", title="Stash", rss="https://feed", source="podcast")
    from ui.show_details_dialog import ShowDetailsDialog

    ctx = _make_ctx(tmp_path, show)
    guids = _seed_episodes(ctx, "stash", 5)
    dlg = ShowDetailsDialog(ctx, "stash")
    _keepalive.append(dlg)

    item = dlg._episodes_tbl.item(0, 0)
    assert item.data(Qt.ItemDataRole.UserRole) == guids[0]
