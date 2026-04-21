"""Failed queue tab."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.state import EpisodeStatus

_REASON_MAP = {
    "SSRFGuardError": "ssrf-guard: private IP",
    "FileTooLargeError": "mp3 > 2GB cap",
    "HashMismatch": "model hash mismatch",
    "TranscriptionError": None,  # None = keep underlying message
    "TimeoutError": "whisper timed out",
}


def _humanise_reason(err: str) -> str:
    if not err:
        return ""
    for key, replacement in _REASON_MAP.items():
        if key in err:
            return replacement or err.split("\n", 1)[0][:120]
    return err.split("\n", 1)[0][:120]


class FailedTab(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        v = QVBoxLayout(self)

        # Toolbar above the table — preserves the existing bulk actions.
        h = QHBoxLayout()
        retry_all = QPushButton("Retry all")
        retry_all.clicked.connect(self._retry_all)
        add_q = QPushButton("Add failed to queue")
        add_q.clicked.connect(self._add_all_to_queue)
        push_top = QPushButton("Push failed on top of queue")
        push_top.clicked.connect(self._push_on_top)
        play = QPushButton("Play MP3")
        play.clicked.connect(self._play_selected)
        play.setToolTip(
            "Open the partial MP3 of the selected row in the default audio app for a spot-check."
        )
        clean = QPushButton("Clear older than 30 days")
        clean.clicked.connect(self._clear_old)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        for b in (retry_all, add_q, push_top, play, clean, refresh):
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Show", "Episode", "Reason", "Tries", "Last attempt", ""]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 40)
        v.addWidget(self.table)

        # guid → raw error text, for Copy-error / Show-log handlers.
        self._errors: dict[str, str] = {}

        self.refresh()

    def refresh(self):
        with self.ctx.state._conn() as c:
            rows = c.execute(
                "SELECT show_slug, guid, title, attempted_at, error_text "
                "FROM episodes WHERE status='failed' ORDER BY attempted_at DESC"
            ).fetchall()
        self.table.setRowCount(0)
        self._errors.clear()
        for r in rows:
            guid = r["guid"]
            row_error = r["error_text"] or ""
            self._errors[guid] = row_error
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["show_slug"] or ""))
            self.table.setItem(row, 1, QTableWidgetItem(r["title"] or ""))
            self.table.setItem(row, 2, QTableWidgetItem(_humanise_reason(row_error)))
            # Tries is not tracked in the schema yet — show a dash.
            self.table.setItem(row, 3, QTableWidgetItem("—"))
            self.table.setItem(row, 4, QTableWidgetItem(r["attempted_at"] or ""))
            # Stash guid on the row (column 0) for selection-based helpers.
            self.table.item(row, 0).setData(0x0100, guid)  # Qt.ItemDataRole.UserRole

            btn = QPushButton("⋯")
            btn.setFlat(True)
            btn.setFixedWidth(28)
            menu = QMenu(btn)
            a_retry = menu.addAction("Retry")
            a_retry.triggered.connect(lambda _=False, g=guid: self._retry_guid(g))
            a_resolve = menu.addAction("Mark resolved")
            a_resolve.triggered.connect(lambda _=False, g=guid: self._mark_resolved(g))
            a_log = menu.addAction("Show log")
            a_log.triggered.connect(lambda _=False, g=guid: self._show_log(g))
            a_copy = menu.addAction("Copy error")
            a_copy.triggered.connect(lambda _=False, g=guid: self._copy_error(g))
            menu.addSeparator()
            a_skip = menu.addAction("Skip forever")
            a_skip.triggered.connect(lambda _=False, g=guid: self._skip_forever(g))
            btn.setMenu(menu)
            self.table.setCellWidget(row, 5, btn)

    # --- Per-row handlers -------------------------------------------------

    def _retry_guid(self, guid: str) -> None:
        self.ctx.state.set_status(guid, EpisodeStatus.PENDING)
        self.refresh()

    def _mark_resolved(self, guid: str) -> None:
        # No SKIPPED value in the enum; write the raw string. set_status's
        # fallback branch handles any status value.
        self.ctx.state.set_status(guid, "skipped")  # type: ignore[arg-type]
        self.refresh()

    def _show_log(self, guid: str) -> None:
        # No per-guid log file exists; surface the captured error text.
        err = self._errors.get(guid) or "(no error text captured)"
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Error log")
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.setText(f"Episode {guid}")
        dlg.setDetailedText(err)
        dlg.exec()

    def _copy_error(self, guid: str) -> None:
        QApplication.clipboard().setText(self._errors.get(guid, ""))

    def _skip_forever(self, guid: str) -> None:
        # Permanent-skip flag in meta, then mark skipped. Retry-all paths
        # can consult skip_forever:<guid> if they want to honour it.
        self.ctx.state.set_meta(f"skip_forever:{guid}", "1")
        self.ctx.state.set_status(guid, "skipped")  # type: ignore[arg-type]
        self.refresh()

    # --- Existing bulk handlers (preserved) -------------------------------

    def _play_selected(self):
        import subprocess
        from pathlib import Path

        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if not rows:
            return
        row = next(iter(rows))
        item = self.table.item(row, 0)
        if item is None:
            return
        guid = item.data(0x0100)
        if not guid:
            return
        with self.ctx.state._conn() as c:
            ep = c.execute(
                "SELECT show_slug, mp3_path FROM episodes WHERE guid=?", (guid,)
            ).fetchone()
        if ep is None:
            return
        mp3 = Path(ep["mp3_path"]) if ep["mp3_path"] else None
        if mp3 and mp3.exists():
            subprocess.run(["open", str(mp3)])

    def _retry_all(self):
        with self.ctx.state._conn() as c:
            c.execute("UPDATE episodes SET status='pending' WHERE status='failed'")
        self.refresh()

    def _clear_old(self):
        with self.ctx.state._conn() as c:
            c.execute(
                "DELETE FROM episodes WHERE status='failed' "
                "AND attempted_at < datetime('now', '-30 days')"
            )
        self.refresh()

    def _add_all_to_queue(self):
        """Mark all failed as pending (priority 0) and kick off a check if idle."""
        with self.ctx.state._conn() as c:
            c.execute("UPDATE episodes SET status='pending', priority=0 WHERE status='failed'")
        self.refresh()
        self._trigger_start()

    def _push_on_top(self):
        """Mark all failed as pending with priority=10 → processed first."""
        with self.ctx.state._conn() as c:
            c.execute("UPDATE episodes SET status='pending', priority=10 WHERE status='failed'")
        self.refresh()
        self._trigger_start()

    def _trigger_start(self):
        # MainWindow exposes .shows_tab, go through it so Stop button wires up.
        win = self.window()
        if hasattr(win, "shows_tab") and not self.ctx.queue.running:
            win.shows_tab.start_check()
