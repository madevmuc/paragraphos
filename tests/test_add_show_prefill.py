"""Regression test for the Shows-search bug: selecting a row (not
double-clicking) must pre-fill the form with in-memory PodcastMatch
data so the user gets immediate feedback."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_app_ref = QApplication.instance() or QApplication([])
_keepalive: list = []


def _make_dialog(tmp_path: Path):
    from ui.add_show_dialog import AddShowDialog
    from ui.app_context import AppContext

    ctx = AppContext.load(tmp_path)
    dlg = AddShowDialog(ctx, None)
    _keepalive.append(dlg)
    return dlg


def test_selecting_a_search_result_row_prefills_form(tmp_path: Path):
    from core.discovery import PodcastMatch

    dlg = _make_dialog(tmp_path)

    # Put two fake matches in the table — network NOT invoked.
    dlg.results.set_matches(
        [
            PodcastMatch(
                title="Lex Fridman Podcast",
                author="Lex Fridman",
                feed_url="https://lexfridman.com/feed/podcast/",
                artwork_url=None,
                itunes_collection_id=None,
            ),
            PodcastMatch(
                title="Beyond Buildings",
                author="m4ma",
                feed_url="https://example.com/feed.rss",
                artwork_url=None,
                itunes_collection_id=None,
            ),
        ]
    )

    # Sanity: before any selection, form fields are empty.
    assert dlg.name_rss.text() == ""
    assert dlg.name_title.text() == ""
    assert dlg.name_slug.text() == ""

    # Simulate row-selection via setCurrentCell (same signal path as a
    # mouse single-click: fires currentCellChanged).
    dlg.results.setCurrentCell(1, 1)  # row 1, title column

    # Pump events for the queued signal to deliver.
    for _ in range(10):
        _app_ref.processEvents()

    # Second match should be pre-filled from in-memory data.
    # No network fetch required.
    assert dlg.name_rss.text() == "https://example.com/feed.rss"
    assert dlg.name_title.text() == "Beyond Buildings"
    assert dlg.name_slug.text() == "beyond-buildings"


def test_switching_selection_updates_form(tmp_path: Path):
    """Changing the selected row must overwrite prior values (no stale
    leftover from a previous selection)."""
    from core.discovery import PodcastMatch

    dlg = _make_dialog(tmp_path)

    dlg.results.set_matches(
        [
            PodcastMatch(
                title="First Show",
                author="A",
                feed_url="https://a.example/r",
                artwork_url=None,
                itunes_collection_id=None,
            ),
            PodcastMatch(
                title="Second Show",
                author="B",
                feed_url="https://b.example/r",
                artwork_url=None,
                itunes_collection_id=None,
            ),
        ]
    )
    dlg.results.setCurrentCell(0, 1)
    for _ in range(10):
        _app_ref.processEvents()
    assert dlg.name_title.text() == "First Show"

    dlg.results.setCurrentCell(1, 1)
    for _ in range(10):
        _app_ref.processEvents()
    assert dlg.name_title.text() == "Second Show"
    assert dlg.name_rss.text() == "https://b.example/r"
    assert dlg.name_slug.text() == "second-show"
