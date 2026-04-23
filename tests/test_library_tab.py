"""LibraryTab — bare-QApplication smoke tests (no pytest-qt).

Mirrors tests/test_settings_pane_sources.py: build a fake AppContext
that's just enough for LibraryTab to construct, refresh, and filter.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.models import Settings, Show, Watchlist
from core.state import StateStore

_QT_KEEPALIVE: list = []


class _FakeCtx:
    """The minimum AppContext surface LibraryTab consumes."""

    def __init__(self, tmp_path: Path):
        self.data_dir = tmp_path
        self.settings = Settings()
        self.settings.output_root = str(tmp_path / "out")
        self.state = StateStore(tmp_path / "state.sqlite")
        self.state.init_schema()
        self.watchlist = Watchlist()
        self.library = None

    def reload_library(self) -> None:  # pragma: no cover
        pass


def _seed_episode(state: StateStore, *, guid: str, slug: str, title: str, pub_date: str) -> None:
    """Insert one row into episodes table directly with status='done'."""
    with state._conn() as c:
        c.execute(
            "INSERT INTO episodes(guid, show_slug, title, pub_date, mp3_url, "
            "status, completed_at, duration_sec) "
            "VALUES (?, ?, ?, ?, '', 'done', ?, ?)",
            (guid, slug, title, pub_date, pub_date + "T00:00:00", 600),
        )


def _make_md(output_root: Path, show_slug: str, pub_date: str, title: str) -> Path:
    """Mirror core.pipeline.build_slug to compute the on-disk filename."""
    from core.pipeline import build_slug

    slug = build_slug(pub_date, title, "0000")
    p = output_root / show_slug / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nguid: x\ntitle: {title}\n---\n\n# {title}\n\nbody\n",
        encoding="utf-8",
    )
    return p


def _make_tab(tmp_path: Path):
    app = QApplication.instance() or QApplication([])
    _QT_KEEPALIVE.append(app)
    from ui.library_tab import LibraryTab

    ctx = _FakeCtx(tmp_path)
    tab = LibraryTab(ctx)
    _QT_KEEPALIVE.append(tab)
    return tab, ctx, app


def test_constructs_with_empty_state(tmp_path):
    tab, _ctx, _app = _make_tab(tmp_path)
    # Tree should have just the "All episodes (0)" pseudo-show node.
    root = tab.tree.invisibleRootItem()
    assert root.childCount() == 1
    assert "All episodes" in root.child(0).text(0)
    assert "(0)" in root.child(0).text(0)
    assert tab.table.rowCount() == 0


def test_lists_done_episodes(tmp_path):
    tab, ctx, app = _make_tab(tmp_path)
    out = Path(ctx.settings.output_root)
    # Two done episodes in the same show with .md files on disk.
    ctx.watchlist.shows.append(
        Show(slug="demo", title="Demo Show", rss="http://x/feed", source="podcast")
    )
    _seed_episode(ctx.state, guid="g1", slug="demo", title="Episode One", pub_date="2026-04-22")
    _seed_episode(ctx.state, guid="g2", slug="demo", title="Episode Two", pub_date="2026-04-21")
    _make_md(out, "demo", "2026-04-22", "Episode One")
    _make_md(out, "demo", "2026-04-21", "Episode Two")
    tab.refresh()
    app.processEvents()
    root = tab.tree.invisibleRootItem()
    # "All episodes (2)" + 1 show node.
    assert root.childCount() == 2
    assert "(2)" in root.child(0).text(0)
    assert tab.table.rowCount() == 2


def test_filter_narrows_list(tmp_path):
    tab, ctx, app = _make_tab(tmp_path)
    out = Path(ctx.settings.output_root)
    ctx.watchlist.shows.append(
        Show(slug="demo", title="Demo Show", rss="http://x/feed", source="podcast")
    )
    _seed_episode(ctx.state, guid="g1", slug="demo", title="Apple Pie", pub_date="2026-04-22")
    _seed_episode(ctx.state, guid="g2", slug="demo", title="Banana Bread", pub_date="2026-04-21")
    _make_md(out, "demo", "2026-04-22", "Apple Pie")
    _make_md(out, "demo", "2026-04-21", "Banana Bread")
    tab.refresh()
    app.processEvents()
    assert tab.table.rowCount() == 2
    tab.filter_edit.setText("apple")
    tab._apply_filter()  # bypass debounce
    assert tab.table.rowCount() == 1
