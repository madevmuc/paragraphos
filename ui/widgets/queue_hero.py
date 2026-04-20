"""Queue run dashboard — big visible card shown only when a run is active."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

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

    def __init__(self, ctx, on_pause: Callable[[], None],
                 on_stop: Callable[[], None], parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._on_pause = on_pause
        self._on_stop = on_stop

        outer = QFrame(self)
        outer.setObjectName("QueueHeroCard")
        outer.setStyleSheet(
            "QFrame#QueueHeroCard { border: 1.5px solid palette(mid); "
            "border-radius: 10px; padding: 14px; }")
        wrap = QVBoxLayout(self); wrap.setContentsMargins(0, 0, 0, 0)
        wrap.addWidget(outer)
        grid = QGridLayout(outer); grid.setHorizontalSpacing(18)

        self.ring = ProgressRing(size=110)
        grid.addWidget(self.ring, 0, 0, 2, 1, Qt.AlignmentFlag.AlignCenter)

        top = QHBoxLayout()
        self.pill = Pill("running", kind="running")
        self.ep_title = QLabel("")
        self.ep_title.setProperty("class", "heading")
        pause = QPushButton("Pause")
        pause.clicked.connect(self._on_pause)
        stop = QPushButton("Stop")
        stop.clicked.connect(self._on_stop)
        top.addWidget(self.pill)
        top.addWidget(self.ep_title, stretch=1)
        top.addWidget(pause)
        top.addWidget(stop)
        top_w = QWidget()
        top_w.setLayout(top)
        grid.addWidget(top_w, 0, 1)

        stats = QGridLayout()
        stats.setHorizontalSpacing(14)
        self.stat_widgets = {}
        labels_map = {"started": "STARTED", "elapsed": "ELAPSED",
                      "per_ep": "PER EP.", "finish": "FINISH \u2248"}
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
            self.hide()
            return
        self.show()
        self.ring.set_progress(q.done, q.total)

        now = datetime.now()
        started = q.started_at
        elapsed = (now - started).total_seconds()
        avg = q.effective_avg_sec
        remaining = max(0, q.total - q.done)
        eta_sec = avg * remaining if avg else 0
        finish = now + timedelta(seconds=eta_sec) if eta_sec else None

        def set_stat(key, value, sub=""):
            self.stat_widgets[key][0].setText(value)
            self.stat_widgets[key][1].setText(sub)

        set_stat("started", started.strftime("%H:%M"),
                 started.strftime("%a \u00b7 %b %d, %Y"))
        set_stat("elapsed", _fmt(elapsed))
        if avg:
            suffix = "" if q.avg_sec_per_episode else "(est.)"
            set_stat("per_ep", f"{int(avg)}s", suffix)
        else:
            set_stat("per_ep", "\u2014")
        if finish:
            frame = human_finish_framing(now, finish)
            sub = finish.strftime("%a \u00b7 %b %d") + (f" \u00b7 {frame}" if frame else "")
            set_stat("finish", finish.strftime("%H:%M"), sub)
            show = q.last_episode_show or ""
            title = q.last_episode_title or ""
            if show or title:
                self.ep_title.setText(f"{show} \u2014 {title}" if show and title else (show or title))
            else:
                self.ep_title.setText("")
        else:
            set_stat("finish", "\u2014")


def _fmt(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"
