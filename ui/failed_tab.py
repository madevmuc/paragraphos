"""Failed queue tab."""

from __future__ import annotations

from PyQt6.QtWidgets import (QHBoxLayout, QHeaderView, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from core.state import EpisodeStatus


class FailedTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        v = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Show", "Title", "Attempted", "Error", "GUID"])
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        v.addWidget(self.table)
        h = QHBoxLayout()
        retry_sel = QPushButton("Retry selected")
        retry_sel.clicked.connect(self._retry)
        retry_all = QPushButton("Retry all")
        retry_all.clicked.connect(self._retry_all)
        add_q = QPushButton("Add failed to queue")
        add_q.clicked.connect(self._add_all_to_queue)
        push_top = QPushButton("Push failed on top of queue")
        push_top.clicked.connect(self._push_on_top)
        clean = QPushButton("Clear older than 30 days")
        clean.clicked.connect(self._clear_old)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        for b in (retry_sel, retry_all, add_q, push_top, clean, refresh):
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        self.refresh()

    def refresh(self):
        with self.ctx.state._conn() as c:
            rows = c.execute(
                "SELECT show_slug, guid, title, attempted_at, error_text "
                "FROM episodes WHERE status='failed' ORDER BY attempted_at DESC"
            ).fetchall()
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["show_slug"] or ""))
            self.table.setItem(row, 1, QTableWidgetItem(r["title"] or ""))
            self.table.setItem(row, 2, QTableWidgetItem(r["attempted_at"] or ""))
            self.table.setItem(row, 3, QTableWidgetItem(r["error_text"] or ""))
            self.table.setItem(row, 4, QTableWidgetItem(r["guid"]))

    def _retry(self):
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        for r in rows:
            guid = self.table.item(r, 4).text()
            self.ctx.state.set_status(guid, EpisodeStatus.PENDING)
        self.refresh()

    def _retry_all(self):
        with self.ctx.state._conn() as c:
            c.execute("UPDATE episodes SET status='pending' WHERE status='failed'")
        self.refresh()

    def _clear_old(self):
        with self.ctx.state._conn() as c:
            c.execute(
                "DELETE FROM episodes WHERE status='failed' "
                "AND attempted_at < datetime('now', '-30 days')")
        self.refresh()

    def _add_all_to_queue(self):
        """Mark all failed as pending (priority 0) and kick off a check if idle."""
        with self.ctx.state._conn() as c:
            c.execute("UPDATE episodes SET status='pending', priority=0 "
                      "WHERE status='failed'")
        self.refresh()
        self._trigger_start()

    def _push_on_top(self):
        """Mark all failed as pending with priority=10 → processed first."""
        with self.ctx.state._conn() as c:
            c.execute("UPDATE episodes SET status='pending', priority=10 "
                      "WHERE status='failed'")
        self.refresh()
        self._trigger_start()

    def _trigger_start(self):
        # MainWindow exposes .shows_tab, go through it so Stop button wires up.
        win = self.window()
        if hasattr(win, "shows_tab") and not self.ctx.queue.running:
            win.shows_tab.start_check()
