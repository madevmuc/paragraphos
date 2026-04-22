"""Rich search-results table for the add-show dialog.

Columns: Cover · Title · Author · Episodes · Latest · Newest episode

Feed-derived cells (Episodes / Latest / Newest) start as '…' placeholders;
the dialog's probe queue populates them as FeedProbeWorker results arrive.
Cover cells are lazy-loaded separately by the dialog (Task 7).
"""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from core.discovery import PodcastMatch

COL_COVER = 0
COL_TITLE = 1
COL_AUTHOR = 2
COL_EPISODES = 3
COL_LATEST = 4
COL_NEWEST = 5
COL_COUNT = 6

ROW_HEIGHT = 52


class ShowResultsTable(QTableWidget):
    """Read-only, single-select table of podcast search matches."""

    def __init__(self, parent=None):
        super().__init__(0, COL_COUNT, parent)
        self.setHorizontalHeaderLabels(
            ["", "Title", "Author", "Episodes", "Latest", "Newest episode"]
        )
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        # Column sizing: cover fixed, title stretches, others fit-to-content.
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(COL_COVER, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(COL_COVER, 56)
        hdr.setSectionResizeMode(COL_TITLE, QHeaderView.ResizeMode.Stretch)
        for col in (COL_AUTHOR, COL_EPISODES, COL_LATEST, COL_NEWEST):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._matches: list[PodcastMatch] = []

    def set_matches(self, matches: Sequence[PodcastMatch]) -> None:
        """Replace all rows. Feed-derived cells start as '…' placeholders
        — they're filled later by apply_probe_result()."""
        self._matches = list(matches)
        self.setRowCount(len(self._matches))
        for row, m in enumerate(self._matches):
            self.setRowHeight(row, ROW_HEIGHT)
            # Cover cell — empty for now; Task 7 fills via set_cover().
            cover = QTableWidgetItem("")
            cover.setFlags(cover.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.setItem(row, COL_COVER, cover)
            self.setItem(row, COL_TITLE, QTableWidgetItem(m.title))
            self.setItem(row, COL_AUTHOR, QTableWidgetItem(m.author))
            self.setItem(row, COL_EPISODES, QTableWidgetItem("\u2026"))
            self.setItem(row, COL_LATEST, QTableWidgetItem("\u2026"))
            self.setItem(row, COL_NEWEST, QTableWidgetItem("\u2026"))

    def feed_url_for_row(self, row: int) -> Optional[str]:
        if 0 <= row < len(self._matches):
            return self._matches[row].feed_url
        return None

    def match_for_row(self, row: int) -> Optional[PodcastMatch]:
        if 0 <= row < len(self._matches):
            return self._matches[row]
        return None

    def apply_probe_result(
        self,
        result: tuple[int, Optional[int], Optional[str], Optional[str]],
    ) -> None:
        """Fill the Episodes / Latest / Newest cells for one row.

        result shape: (row_index, ep_count|None, latest_iso|None, latest_title|None).
        None counts/dates render as em-dash ("—") so failed probes are
        visually distinct from still-loading '…' placeholders.
        """
        row, n, date, title = result
        if not (0 <= row < self.rowCount()):
            return
        dash = "\u2014"
        self.item(row, COL_EPISODES).setText(str(n) if n is not None else dash)
        self.item(row, COL_LATEST).setText(date[:10] if date else dash)
        self.item(row, COL_NEWEST).setText(title if title else dash)

    def set_cover(self, row: int, pixmap: QPixmap) -> None:
        """Called by the dialog's cover loader — sets the icon on the
        cover cell. Pixmap should be ~48 px high (fits the row height)."""
        if not (0 <= row < self.rowCount()):
            return
        from PyQt6.QtGui import QIcon

        item = self.item(row, COL_COVER)
        if item is None:
            return
        item.setIcon(QIcon(pixmap))
