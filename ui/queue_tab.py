"""Queue tab — live view of pending/in-flight episodes + progress summary."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.prioritize import (
    PRIORITY_RUN_NEXT,
    PRIORITY_RUN_NOW,
    bump_priority,
    can_bump,
)
from ui.retranscribe import retranscribe_episode
from ui.widgets.queue_hero import QueueHero


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

        # Big-visible hero dashboard shown only while a run is active.
        self.hero = QueueHero(
            ctx,
            on_pause=self._pause,
            on_stop=self._stop,
            parent=self,
        )
        v.addWidget(self.hero)

        # Header — status summary
        self.header = QLabel()
        self.header.setStyleSheet(
            "padding:8px 12px; background:palette(alternate-base); border-radius:4px;"
        )
        self.header.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.header)

        # Subtle advisory banner — shown only when parallel_transcribe or
        # whisper_multiproc diverge from the HW-based recommendation. Lets
        # the user know they're leaving performance on the table without
        # being nagged with a modal dialog.
        self._tuning_hint = QLabel()
        self._tuning_hint.setWordWrap(True)
        self._tuning_hint.setTextFormat(Qt.TextFormat.RichText)
        self._tuning_hint.setOpenExternalLinks(False)
        self._tuning_hint.setStyleSheet("padding:6px 10px; font-size:11px; color:#b8864a;")
        self._tuning_hint.hide()
        v.addWidget(self._tuning_hint)
        self._refresh_tuning_hint()

        # Table of pending episodes
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Show",
                "Pub Date",
                "Ep#",
                "Title",
                "Status",
                "Audio",
                "Whisper",
                "Finish ≈",
            ]
        )
        _hdr = self.table.horizontalHeader()
        _hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # Auto-fit everything except Status — Status has a fixed width
        # so the live "transcribing · XXX%" update doesn't resize the
        # column (and cascade a layout twitch) every second.
        for _col in (0, 1, 2, 5, 6, 7):
            _hdr.setSectionResizeMode(_col, QHeaderView.ResizeMode.ResizeToContents)
        _hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 150)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
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

        # Table rebuild throttle: coalesce refresh requests so we rebuild
        # at most once per 3 s even when episodes finish in bursts.
        self._last_table_refresh = 0.0
        self._refresh_pending = False

        self.refresh()

    def _tick(self):
        self._tick_header()
        self._update_btns()
        self._refresh_tuning_hint()
        # Rebuild the table too — the refresh() call is throttled to
        # 3 s internally, so firing every second just keeps the
        # coalesce-window warm. Without this, the table only updated
        # on on_queue_sized / on_episode_done / on_finished_all signals,
        # which meant status transitions mid-queue (downloaded →
        # transcribing) stayed invisible for minutes.
        self.refresh()

    def _refresh_tuning_hint(self) -> None:
        """Show a muted 'nicht-empfohlen'-hinweis when parallel_transcribe
        or whisper_multiproc diverge from the HW recommendation. Subtle —
        amber text on the tab background, no border/bg. Hidden when in
        line with the recommendation or when detect fails."""
        try:
            from core.hw import (
                detect,
                recommended_multiproc_split,
                recommended_parallel_workers,
            )
        except Exception:
            self._tuning_hint.hide()
            return
        _, ncpu = detect()
        if ncpu is None:
            self._tuning_hint.hide()
            return
        rec_par = recommended_parallel_workers()
        rec_mp = recommended_multiproc_split()
        cur_par = int(self.ctx.settings.parallel_transcribe or 1)
        cur_mp = int(self.ctx.settings.whisper_multiproc or 1)
        mismatches = []
        if cur_par != rec_par:
            mismatches.append(f"parallel workers: {cur_par} → {rec_par}")
        if cur_mp != rec_mp:
            mismatches.append(f"multi-processor split: {cur_mp} → {rec_mp}")
        if not mismatches:
            self._tuning_hint.hide()
            return
        self._tuning_hint.setText(
            "ⓘ Tipp: " + " · ".join(mismatches) + " — anpassen in Settings für beste Laufzeit."
        )
        self._tuning_hint.show()

    # ── public hooks wired from ShowsTab/worker ───────────────

    def on_queue_sized(self, total: int) -> None:
        self._total = total
        self._done = 0
        self._started_at = datetime.now()
        self._episode_durations = []
        self._last_ep_start = datetime.now()
        self.refresh()

    def on_episode_done(
        self,
        slug: str,
        guid: str,
        action: str,
        done_idx: int,
        total: int,
        show_title: str,
        ep_title: str,
    ) -> None:
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
        # Queue tab Start is always user-initiated → bypass feed backoff.
        self._shows_tab().start_check(force=True)
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
        import time

        now = time.monotonic()
        self._tick_header()
        if now - self._last_table_refresh < 3.0:
            if not self._refresh_pending:
                self._refresh_pending = True
                delay_ms = int((3.0 - (now - self._last_table_refresh)) * 1000)
                QTimer.singleShot(max(delay_ms, 0), self._deferred_refresh)
            return
        self._last_table_refresh = now
        self._refresh_table()

    def _deferred_refresh(self) -> None:
        import time

        self._refresh_pending = False
        self._last_table_refresh = time.monotonic()
        self._refresh_table()
        self._tick_header()

    def _tick_header(self) -> None:
        self.header.setText(self._format_header())

    def _format_header(self) -> str:
        with self.ctx.state._conn() as c:
            status_counts = {}
            for row in c.execute("SELECT status, COUNT(*) FROM episodes GROUP BY status"):
                status_counts[row[0]] = row[1]
        pending_total = status_counts.get("pending", 0)
        done_total = status_counts.get("done", 0)
        failed = status_counts.get("failed", 0)

        if self._started_at is None or self._total == 0:
            return (
                f"<b>Queue</b> — pending: {pending_total} · "
                f"done: {done_total} · failed: {failed} · "
                "<i>idle (click Start on any tab to run)</i>"
            )

        elapsed = datetime.now() - self._started_at
        live_avg = (
            sum(self._episode_durations) / len(self._episode_durations)
            if self._episode_durations
            else 0
        )
        # Fall back to shared state — its historical DB estimate is populated
        # at start_check so "finish ≈" is shown from t=0.
        avg = live_avg or self.ctx.queue.effective_avg_sec
        remaining = self._total - self._done
        # Prefer duration-based ETA (pending audio × realtime factor)
        # when available — the per-episode average is a last resort.
        duration_eta = self.ctx.queue.duration_based_eta_sec
        if duration_eta > 0:
            eta_sec = duration_eta
        else:
            eta_sec = avg * remaining if avg else 0
        finish_at = datetime.now() + timedelta(seconds=eta_sec) if eta_sec else None

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
        from datetime import datetime, timedelta

        from core.stats import realtime_factor

        rtf = realtime_factor(self.ctx.state)
        cumulative_wall = 0.0  # seconds already committed above this row
        now = datetime.now()

        with self.ctx.state._conn() as c:
            rows = c.execute(
                "SELECT show_slug, pub_date, title, status, guid, duration_sec "
                "FROM episodes "
                "WHERE status IN ('pending','downloading','downloaded','transcribing') "
                # Active stages first (transcribing → downloaded →
                # downloading), then pending by priority + date. Without
                # this CASE, a large 'pending' backlog would push in-flight
                # rows past the LIMIT 500 cutoff and hide parallel workers
                # from the UI.
                "ORDER BY "
                "  CASE status "
                "    WHEN 'transcribing' THEN 0 "
                "    WHEN 'downloaded'   THEN 1 "
                "    WHEN 'downloading'  THEN 2 "
                "    ELSE 3 "
                "  END, "
                "  priority DESC, pub_date DESC"
            ).fetchall()
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            show_item = QTableWidgetItem(r["show_slug"])
            # Stash the guid on the first-column item so the context menu
            # can retrieve it via UserRole data.
            show_item.setData(Qt.ItemDataRole.UserRole, r["guid"])
            self.table.setItem(row, 0, show_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["pub_date"]))
            self.table.setItem(row, 2, QTableWidgetItem(""))  # episode_number not in state
            self.table.setItem(row, 3, QTableWidgetItem(r["title"]))
            # Status column — for transcribing rows, read the live
            # percent meta written by core.pipeline.transcribe_phase.
            status_text = r["status"]
            if status_text == "transcribing":
                pct = self.ctx.state.get_meta(f"transcribe_pct:{r['guid']}") or ""
                if pct.isdigit():
                    status_text = f"transcribing · {pct}%"
            status_item = QTableWidgetItem(status_text)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, status_item)

            # Audio length (mm:ss or h:mm:ss)
            dur_sec = int(r["duration_sec"] or 0)
            self.table.setItem(row, 5, QTableWidgetItem(_fmt_hms(dur_sec) if dur_sec else "—"))
            # Whisper wall-clock estimate (audio × realtime_factor)
            whisper_sec = int(dur_sec * rtf) if dur_sec else 0
            self.table.setItem(
                row, 6, QTableWidgetItem(_fmt_hms(whisper_sec) if whisper_sec else "—")
            )
            # Finish ≈ — cumulative, so row N reflects "done after all
            # earlier rows in the queue have finished".
            if whisper_sec:
                cumulative_wall += whisper_sec
                finish_at = now + timedelta(seconds=cumulative_wall)
                self.table.setItem(row, 7, QTableWidgetItem(_fmt_finish(finish_at)))
            else:
                self.table.setItem(row, 7, QTableWidgetItem("—"))

    # ── context menu ──────────────────────────────────────────

    def _on_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        item = self.table.item(index.row(), 0)
        if item is None:
            return
        guid = item.data(Qt.ItemDataRole.UserRole)
        if not guid:
            return
        status_item = self.table.item(index.row(), 4)
        status = status_item.text() if status_item is not None else ""
        menu = QMenu(self)
        menu.addAction(
            "Re-transcribe this episode",
            lambda g=guid: self._retranscribe(g),
        )
        if can_bump(status):
            menu.addSeparator()
            menu.addAction(
                "Run next",
                lambda g=guid: self._bump(g, PRIORITY_RUN_NEXT),
            )
            menu.addAction(
                "Run now",
                lambda g=guid: self._bump(g, PRIORITY_RUN_NOW),
            )
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _retranscribe(self, guid: str) -> None:
        retranscribe_episode(self.ctx, guid)
        self.refresh()

    def _bump(self, guid: str, priority: int) -> None:
        bump_priority(self.ctx, guid, priority)
        # Force a full rebuild so the new sort order is reflected immediately,
        # bypassing the 3-second refresh coalescing.
        import time

        self._last_table_refresh = time.monotonic()
        self._refresh_table()


def _fmt_duration(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h}h {m}m"


def _fmt_hms(sec: int) -> str:
    """Compact mm:ss for <1h, h:mm:ss otherwise."""
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_finish(dt) -> str:
    """HH:MM today; 'Mon HH:MM' when future day."""
    from datetime import datetime

    now = datetime.now()
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    if (dt.date() - now.date()).days < 7:
        return dt.strftime("%a %H:%M")
    return dt.strftime("%b %d %H:%M")
