"""Queue run dashboard — big visible card shown only when a run is active."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.widgets import Pill, ProgressRing


def human_finish_framing(now: datetime, finish: datetime) -> str:
    """Return human phrase for when the run finishes."""
    delta = (finish - now).total_seconds()
    if delta < 30 * 60:
        return "soon"
    if finish.date() == now.date():
        h = finish.hour
        if h < 12:
            return "before lunch"
        if h < 14:
            return "around lunch"
        if h < 17:
            return "this afternoon"
        if h < 20:
            return "this evening"
        return "tonight"
    if (finish.date() - now.date()).days == 1:
        return "tomorrow morning" if finish.hour < 12 else "tomorrow"
    return ""


class QueueHero(QWidget):
    """Composite card: ProgressRing on the left, stats grid on the right."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

        # Styling comes from the global QSS (QFrame#QueueHeroCard rule
        # in ui/themes/app.qss.tmpl) — border color + bg flip with the
        # active theme automatically.
        outer = QFrame(self)
        outer.setObjectName("QueueHeroCard")
        wrap = QVBoxLayout(self)
        wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(outer)
        grid = QGridLayout(outer)
        grid.setHorizontalSpacing(18)

        self.ring = ProgressRing(size=110)
        grid.addWidget(self.ring, 0, 0, 2, 1, Qt.AlignmentFlag.AlignCenter)

        top = QHBoxLayout()
        self.pill = Pill("running", kind="running")
        self.ep_title = QLabel("")
        self.ep_title.setProperty("class", "heading")
        # Episode titles can be very long — without this, the QLabel's
        # minimumSizeHint equals the text pixel width and propagates up
        # the layout chain, forcing QMainWindow to grow to fit. Cap the
        # label's horizontal demand so the window stays where the user
        # put it; long titles get elided in setText via QFontMetrics.
        self.ep_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.ep_title.setMinimumWidth(0)
        # Pause/Stop buttons live in the QueueTab toolbar at the top of the
        # page (consolidated 2026-04-23). The hero card now only renders
        # state — the toolbar is the single source for queue-control
        # actions so users never see duplicate Pause/Stop buttons.
        top.addWidget(self.pill)
        top.addWidget(self.ep_title, stretch=1)
        top_w = QWidget()
        top_w.setLayout(top)
        grid.addWidget(top_w, 0, 1)

        stats = QGridLayout()
        stats.setHorizontalSpacing(14)
        self.stat_widgets = {}
        labels_map = {
            "started": "STARTED",
            "elapsed": "ELAPSED",
            "per_ep": "PER EP.",
            "finish": "FINISH \u2248",
        }
        for col, key in enumerate(("started", "elapsed", "per_ep", "finish")):
            mini = QLabel(labels_map[key])
            mini.setProperty("class", "mini-label")
            value = QLabel("\u2014")
            value.setProperty("class", "mono")
            value.setStyleSheet("font-size: 15px; font-weight: 600;")
            sub = QLabel("")
            sub.setProperty("class", "muted")
            sub.setStyleSheet("font-size: 11px;")
            stats.addWidget(mini, 0, col)
            stats.addWidget(value, 1, col)
            stats.addWidget(sub, 2, col)
            self.stat_widgets[key] = (value, sub)
        stats_w = QWidget()
        stats_w.setLayout(stats)
        grid.addWidget(stats_w, 1, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)
        self.refresh()

    def refresh(self) -> None:
        q = self.ctx.queue
        if not q.running or not q.started_at:
            # Idle state — keep the card visible. ProgressRing renders a
            # grey pause glyph; pill turns 'idle'; pause/stop disabled;
            # stats reset to dashes. The QSS gives the idle card a muted
            # border via the dynamic 'state' property below.
            self.show()
            self.setProperty("state", "idle")
            self.style().unpolish(self)
            self.style().polish(self)
            self.ring.set_idle(True)
            self.pill.set_kind("idle")
            self.pill.setText("idle")
            self.ep_title.setText("Queue is idle. Click Start to begin a check pass.")
            self.ep_title.setToolTip("")
            for value, sub in self.stat_widgets.values():
                value.setText("—")
                sub.setText("")
            return
        self.show()
        self.setProperty("state", "active")
        self.style().unpolish(self)
        self.style().polish(self)
        self.ring.set_idle(False)
        self.pill.set_kind("running")
        self.pill.setText("running")
        self.ring.set_progress(q.done, q.total)

        now = datetime.now()
        started = q.started_at
        elapsed = (now - started).total_seconds()
        avg = q.effective_avg_sec
        remaining = max(0, q.total - q.done)
        # Prefer duration-based ETA (pending audio × realtime factor) —
        # more accurate than episode-count × avg when show episode
        # lengths vary. Falls back to the legacy avg path for empty
        # duration data (e.g. freshly imported feeds).
        duration_eta = q.duration_based_eta_sec
        if duration_eta > 0:
            eta_sec = duration_eta
        else:
            eta_sec = avg * remaining if avg else 0
        finish = now + timedelta(seconds=eta_sec) if eta_sec else None

        def set_stat(key, value, sub=""):
            self.stat_widgets[key][0].setText(value)
            self.stat_widgets[key][1].setText(sub)

        set_stat("started", started.strftime("%H:%M"), started.strftime("%a \u00b7 %b %d, %Y"))
        set_stat("elapsed", _fmt(elapsed))
        from core.stats import has_realtime_history

        has_history = has_realtime_history(self.ctx.state)
        if avg:
            suffix = "" if q.avg_sec_per_episode else "(est.)"
            set_stat("per_ep", f"{int(avg)}s", suffix)
        elif not has_history:
            set_stat("per_ep", "\u2014", "after 1st run")
        else:
            set_stat("per_ep", "\u2014")
        if finish:
            frame = human_finish_framing(now, finish)
            sub = finish.strftime("%a \u00b7 %b %d") + (f" \u00b7 {frame}" if frame else "")
            set_stat("finish", finish.strftime("%H:%M"), sub)
            show = q.last_episode_show or ""
            title = q.last_episode_title or ""
            if show or title:
                full = f"{show} \u2014 {title}" if show and title else (show or title)
                # Elide at the label's current width so we never push the
                # layout wider than the window already is.
                fm = QFontMetrics(self.ep_title.font())
                width = max(80, self.ep_title.width() - 8)
                self.ep_title.setText(fm.elidedText(full, Qt.TextElideMode.ElideRight, width))
                self.ep_title.setToolTip(full)
            else:
                self.ep_title.setText("")
                self.ep_title.setToolTip("")
        else:
            sub = "after 1st run" if not has_history else ""
            set_stat("finish", "\u2014", sub)


def _fmt(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"
