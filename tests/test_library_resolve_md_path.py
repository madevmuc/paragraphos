"""``LibraryTab._resolve_md_path`` slug-drift recovery.

Pre-2026-05-04 the Library tab reconstructed the .md filename with
``episode_number="0000"``. Real downloads write the file under the
actual episode number from the feed (`_0314_`, `_0644_`, …), so the
constructed path didn't exist and the row was silently dropped from
the Library tree. User impact: most recent episodes stopped appearing
in Library even though state.sqlite had them as ``done`` and the
files were on disk.
"""

from __future__ import annotations

# Late import to avoid PyQt6 startup cost when collecting other tests.
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_app_ref = QApplication.instance() or QApplication([])


def _make_tab(tmp_path):
    """Construct a LibraryTab with a stub ctx pointing at tmp_path."""
    from ui.library_tab import LibraryTab

    state = MagicMock()
    state._conn.return_value.__enter__.return_value.execute.return_value = []
    settings = SimpleNamespace(output_root=str(tmp_path))
    watchlist = SimpleNamespace(shows=[])
    ctx = SimpleNamespace(state=state, settings=settings, watchlist=watchlist)
    return LibraryTab(ctx)


def test_resolve_md_path_finds_canonical_zero_slug(tmp_path):
    """Show that genuinely uses _0000_ in the on-disk filename — the
    canonical-path branch hits, no glob needed."""
    show = tmp_path / "lagebericht"
    show.mkdir()
    f = show / "2026-04-29_0000_#260 Sugar Valley.md"
    f.write_text("---\nguid: x\n---\n")

    tab = _make_tab(tmp_path)
    out = tab._resolve_md_path("lagebericht", "2026-04-29", "#260 Sugar Valley")
    assert out == f


def test_resolve_md_path_finds_real_episode_number_via_glob(tmp_path):
    """Real-world case: download wrote `_0314_` because the feed
    carried that episode number. Library row has no ep-num context.
    Pre-fix this missed; post-fix the glob picks it up."""
    show = tmp_path / "limmo"
    show.mkdir()
    f = show / "2026-05-04_0314_Aufstockung, Nachverdichtung, Umnutzung - raus aus der Krise.md"
    f.write_text("---\nguid: l\n---\n")

    tab = _make_tab(tmp_path)
    out = tab._resolve_md_path(
        "limmo",
        "2026-05-04",
        "Aufstockung, Nachverdichtung, Umnutzung - raus aus der Krise",
    )
    assert out == f


def test_resolve_md_path_refuses_date_only_match(tmp_path):
    """Two different episodes published the same day — the glob must
    title-scope so we don't return a wrong-title transcript."""
    show = tmp_path / "limmo"
    show.mkdir()
    other = show / "2026-05-04_0315_Eine ganz andere Folge.md"
    other.write_text("---\nguid: o\n---\n")

    tab = _make_tab(tmp_path)
    out = tab._resolve_md_path("limmo", "2026-05-04", "Aufstockung Nachverdichtung Umnutzung")
    assert out is None


def test_resolve_md_path_picks_newest_when_ambiguous(tmp_path):
    """Same date + title fragment matches two files — prefer the most
    recently modified (the latest re-transcribe)."""
    import time

    show = tmp_path / "limmo"
    show.mkdir()
    older = show / "2026-05-04_0314_Aufstockung Nachverdichtung Umnutzung Teil 1.md"
    older.write_text("---\nguid: a\n---\n")
    time.sleep(0.01)
    newer = show / "2026-05-04_0315_Aufstockung Nachverdichtung Umnutzung Teil 2.md"
    newer.write_text("---\nguid: b\n---\n")

    tab = _make_tab(tmp_path)
    out = tab._resolve_md_path("limmo", "2026-05-04", "Aufstockung Nachverdichtung Umnutzung")
    assert out == newer


def test_resolve_md_path_returns_none_for_missing_show_dir(tmp_path):
    tab = _make_tab(tmp_path)
    out = tab._resolve_md_path("ghost-show", "2026-05-04", "Whatever")
    assert out is None


def test_resolve_md_path_returns_none_for_blank_pub_date(tmp_path):
    show = tmp_path / "limmo"
    show.mkdir()
    (show / "2026-05-04_0314_Aufstockung.md").write_text("---\n---\n")

    tab = _make_tab(tmp_path)
    out = tab._resolve_md_path("limmo", "", "Aufstockung")
    assert out is None
