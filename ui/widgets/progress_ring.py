"""Circular progress ring for the Queue hero.

Thin stroke (4 px) around a 110×110 area. Accent sweep clockwise from
12 o'clock, `ring_track` for the remainder. Centered text shows the
fraction + percent.

Theme-aware: reads colors from `ui.themes.manager().tokens()` at every
paint and subscribes to `themeChanged` for immediate repaint when the
user flips macOS Appearance.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ui.themes import manager
from ui.themes.tokens import LIGHT


def _qcolor(value: str) -> QColor:
    """Parse a token string (`#rrggbb` or `rgba(r, g, b, a)`) into a
    QColor. Qt's QColor.fromString is locale-picky so we roll our own
    for the tiny rgba subset we use."""
    v = value.strip()
    if v.startswith("rgba"):
        inside = v[v.index("(") + 1 : v.rindex(")")]
        parts = [p.strip() for p in inside.split(",")]
        r, g, b = (int(x) for x in parts[:3])
        a = float(parts[3]) if len(parts) == 4 else 1.0
        return QColor(r, g, b, int(round(a * 255)))
    c = QColor()
    c.setNamedColor(v)
    return c


class ProgressRing(QWidget):
    def __init__(self, size: int = 110, stroke: int = 4, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._stroke = stroke
        self._done = 0
        self._total = 0
        # When idle, the centre shows a pause glyph (two vertical bars)
        # instead of the running fraction, and the accent sweep is
        # replaced by a single full muted track. Used by QueueHero to
        # keep the dashboard visible across active + idle states.
        self._idle = False

        tm = manager()
        if tm is not None:
            tm.themeChanged.connect(self._on_theme_changed)

    def set_progress(self, done: int, total: int) -> None:
        self._done = max(0, done)
        self._total = max(0, total)
        self.update()

    def set_idle(self, idle: bool) -> None:
        if self._idle == bool(idle):
            return
        self._idle = bool(idle)
        self.update()

    def _on_theme_changed(self, _mode: str) -> None:
        # paintEvent re-reads tokens; just schedule the repaint.
        self.update()

    def _tokens(self) -> dict[str, str]:
        tm = manager()
        return tm.tokens() if tm is not None else LIGHT

    def paintEvent(self, _ev) -> None:
        t = self._tokens()
        accent = _qcolor(t["accent"])
        track = _qcolor(t["ring_track"])
        ink = _qcolor(t["ink"])
        ink_3 = _qcolor(t["ink_3"])

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(self._stroke, self._stroke, -self._stroke, -self._stroke)

        # Track
        p.setPen(QPen(track, self._stroke))
        p.drawEllipse(r)

        if self._idle:
            # Idle: full grey ring + centred pause glyph (two vertical
            # bars). No accent sweep, no fraction text — keeps the card
            # visible without giving the impression that anything is
            # actually progressing.
            p.setPen(QPen(ink_3, self._stroke, cap=Qt.PenCapStyle.RoundCap))
            p.drawEllipse(r)
            p.setBrush(ink_3)
            p.setPen(Qt.PenStyle.NoPen)
            cx = self.rect().center().x()
            cy = self.rect().center().y()
            bar_w = 7
            bar_h = 26
            gap = 6
            from PyQt6.QtCore import QRect

            p.drawRoundedRect(QRect(cx - bar_w - gap // 2, cy - bar_h // 2, bar_w, bar_h), 2, 2)
            p.drawRoundedRect(QRect(cx + gap // 2, cy - bar_h // 2, bar_w, bar_h), 2, 2)
            p.end()
            return

        # Accent sweep
        if self._total > 0:
            frac = self._done / self._total
            p.setPen(QPen(accent, self._stroke, cap=Qt.PenCapStyle.RoundCap))
            # Qt arc: angles in 1/16 deg; 0° is 3 o'clock, counter-clockwise positive.
            # Start at 12 o'clock (90°), sweep clockwise → negative span.
            start = 90 * 16
            span = -int(frac * 360 * 16)
            p.drawArc(r, start, span)

        # Centered text — fraction + percent.
        p.setPen(ink)
        f_big = QFont()
        f_big.setPointSize(20)
        f_big.setBold(True)
        p.setFont(f_big)
        txt = f"{self._done}/{self._total}" if self._total else "—"
        p.drawText(self.rect().adjusted(0, -8, 0, 0), Qt.AlignmentFlag.AlignCenter, txt)
        f_small = QFont()
        f_small.setPointSize(10)
        p.setFont(f_small)
        p.setPen(ink_3)
        pct = f"{int((self._done / self._total) * 100)}%" if self._total else ""
        p.drawText(self.rect().adjusted(0, 18, 0, 0), Qt.AlignmentFlag.AlignCenter, pct)
        p.end()
