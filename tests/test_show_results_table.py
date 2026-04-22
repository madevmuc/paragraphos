import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.discovery import PodcastMatch
from ui.widgets.show_results_table import ShowResultsTable


def _match(title="Show", author="Author", feed="https://e/r", art=None, coll_id=42):
    return PodcastMatch(
        title=title,
        author=author,
        feed_url=feed,
        artwork_url=art,
        itunes_collection_id=coll_id,
    )


def test_set_matches_renders_placeholders():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A"), _match(title="B")])
    assert tbl.rowCount() == 2
    assert tbl.item(0, 1).text() == "A"
    assert tbl.item(0, 3).text() == "\u2026"  # episodes placeholder
    assert tbl.item(0, 4).text() == "\u2026"  # latest placeholder
    assert tbl.item(0, 5).text() == "\u2026"  # newest placeholder


def test_apply_probe_result_fills_cells():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A")])
    tbl.apply_probe_result((0, 12, "2024-12-01T00:00:00", "Newest Ep"))
    assert tbl.item(0, 3).text() == "12"
    assert tbl.item(0, 4).text() == "2024-12-01"
    assert tbl.item(0, 5).text() == "Newest Ep"


def test_apply_probe_failure_shows_emdash():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A")])
    tbl.apply_probe_result((0, None, None, None))
    assert tbl.item(0, 3).text() == "\u2014"
    assert tbl.item(0, 4).text() == "\u2014"
    assert tbl.item(0, 5).text() == "\u2014"


def test_feed_url_for_row():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A", feed="https://a"), _match(title="B", feed="https://b")])
    assert tbl.feed_url_for_row(0) == "https://a"
    assert tbl.feed_url_for_row(1) == "https://b"
    assert tbl.feed_url_for_row(2) is None


def test_apply_probe_for_out_of_range_row_is_noop():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A")])
    # Should not raise on an out-of-range row.
    tbl.apply_probe_result((99, 5, "2024-12-01T00:00:00", "Oops"))
    assert tbl.item(0, 3).text() == "\u2026"  # unchanged
