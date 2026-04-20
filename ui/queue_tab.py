"""Queue tab — live view of pending/in-flight episodes + progress summary."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)


class QueueTab(QWidget):
    """Shows current queue + progress header with started/elapsed/ETA.

    The worker thread only lives while a check runs. When no thread is active,
    the queue table shows all `pending` episodes; status header shows totals
    from the state DB.
    """

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self._total = 0
        self._done = 0
        self._started_at: datetime | None = None
        self._episode_durations: list[float] = []
        self._last_ep_start: datetime | None = None

        v = QVBoxLayout(self)

        # Header — status summary
        self.header = QLabel()
        self.header.setStyleSheet(
            "padding:8px 12px; background:palette(alternate-base); border-radius:4px;")
        self.header.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.header)

        # Table of pending episodes
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Show", "Pub Date", "Ep#", "Title", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.table)

        h = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start)
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._pause)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self._stop)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        for b in (self.start_btn, self.pause_btn, self.stop_btn, refresh):
            h.addWidget(b)
        h.addStretch()
        v.addLayout(h)
        self._update_btns()

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

        self.refresh()

    def _tick(self):
        self._tick_header()
        self._update_btns()

    # ── public hooks wired from ShowsTab/worker ───────────────

    def on_queue_sized(self, total: int) -> None:
        self._total = total
        self._done = 0
        self._started_at = datetime.now()
        self._episode_durations = []
        self._last_ep_start = datetime.now()
        self.refresh()

    def on_episode_done(self, slug: str, guid: str, action: str,
                        done_idx: int, total: int,
                        show_title: str, ep_title: str) -> None:
        self._done = done_idx
        self._total = total
        now = datetime.now()
        if self._last_ep_start is not None:
            self._episode_durations.append((now - self._last_ep_start).total_seconds())
            self._episode_durations = self._episode_durations[-10:]
        self._last_ep_start = now
        self.refresh()

    def on_finished_all(self) -> None:
        self._last_ep_start = None
        self.refresh()
        self._update_btns()

    def _shows_tab(self):
        return self.window().shows_tab  # MainWindow exposes shows_tab

    def _start(self):
        # If paused, resume (clears paused flag); else just start a check.
        paused = self.ctx.state.get_meta("queue_paused") == "1"
        if paused:
            self.ctx.state.set_meta("queue_paused", "0")
        self._shows_tab().start_check()
        self._update_btns()

    def _pause(self):
        self._shows_tab()._pause()
        self._update_btns()

    def _stop(self):
        self._shows_tab()._stop()
        self._update_btns()

    def _update_btns(self):
        running = self.ctx.queue.running
        paused = self.ctx.state.get_meta("queue_paused") == "1"
        self.start_btn.setEnabled(not running)
        self.start_btn.setText("Resume" if paused else "Start")
        self.pause_btn.setEnabled(running and not paused)
        self.stop_btn.setEnabled(running)

    # ── rendering ─────────────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_table()
        self._tick_header()

    def _tick_header(self) -> None:
        self.header.setText(self._format_header())

    def _format_header(self) -> str:
        with self.ctx.state._conn() as c:
            status_counts = {}
            for row in c.execute(
                "SELECT status, COUNT(*) FROM episodes GROUP BY status"):
                status_counts[row[0]] = row[1]
        pending_total = status_counts.get("pending", 0)
        done_total = status_counts.get("done", 0)
        failed = status_counts.get("failed", 0)

        if self._started_at is None or self._total == 0:
            return (f"<b>Queue</b> — pending: {pending_total} · "
                    f"done: {done_total} · failed: {failed} · "
                    "<i>idle (click Start on any tab to run)</i>")

        elapsed = datetime.now() - self._started_at
        live_avg = (sum(self._episode_durations) / len(self._episode_durations)
                    if self._episode_durations else 0)
        # Fall back to shared state — its historical DB estimate is populated
        # at start_check so "finish ≈" is shown from t=0.
        avg = live_avg or self.ctx.queue.effective_avg_sec
        remaining = self._total - self._done
        eta_sec = avg * remaining if avg else 0
        finish_at = (datetime.now() + timedelta(seconds=eta_sec)
                     if eta_sec else None)

        from ui.main_window import _fmt_dt_locale
        parts = [
            f"<b>Running</b>: {self._done}/{self._total}",
            f"started: {_fmt_dt_locale(self._started_at)}",
            f"elapsed: {_fmt_duration(elapsed.total_seconds())}",
        ]
        if avg:
            per_ep_tag = "avg/ep" if live_avg else "est/ep"
            eta_tag = "ETA" if live_avg else "ETA (est.)"
            parts.append(f"{per_ep_tag}: {avg:.0f}s")
            parts.append(f"{eta_tag}: {_fmt_duration(eta_sec)}")
            if finish_at:
                parts.append(f"finish ≈ {_fmt_dt_locale(finish_at)}")
        return " · ".join(parts)

    def _refresh_table(self) -> None:
        with self.ctx.state._conn() as c:
            rows = c.execute(
                "SELECT show_slug, pub_date, title, status, guid "
                "FROM episodes "
                "WHERE status IN ('pending','downloading','downloaded','transcribing') "
                "ORDER BY status DESC, pub_date DESC LIMIT 500"
            ).fetchall()
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["show_slug"]))
            self.table.setItem(row, 1, QTableWidgetItem(r["pub_date"]))
            self.table.setItem(row, 2, QTableWidgetItem(""))  # episode_number not in state
            self.table.setItem(row, 3, QTableWidgetItem(r["title"]))
            self.table.setItem(row, 4, QTableWidgetItem(r["status"]))


def _fmt_duration(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    h = sec // 3600; m = (sec % 3600) // 60
    return f"{h}h {m}m"
