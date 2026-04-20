"""Circular progress ring for the Queue hero.

Thin stroke (4 px) around a 110×110 area. Accent sweep clockwise from
12 o'clock, `line-soft` for the remainder. Centered text shows the
fraction + percent.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class ProgressRing(QWidget):
    def __init__(self, size: int = 110, stroke: int = 4, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._stroke = stroke
        self._done = 0
        self._total = 0
        self._accent = QColor(180, 122, 58)        # TOKENS['accent']
        self._track = QColor(0, 0, 0, 50)           # 'line-soft' rough equivalent

    def set_progress(self, done: int, total: int) -> None:
        self._done = max(0, done)
        self._total = max(0, total)
        self.update()

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(self._stroke, self._stroke,
                                  -self._stroke, -self._stroke)

        # Track
        p.setPen(QPen(self._track, self._stroke))
        p.drawEllipse(r)

        # Accent sweep
        if self._total > 0:
            frac = self._done / self._total
            p.setPen(QPen(self._accent, self._stroke, cap=Qt.PenCapStyle.RoundCap))
            # Qt arc: angles in 1/16 deg; 0° is 3 o'clock, clockwise negative.
            # Start at 12 o'clock (90°), sweep clockwise → negative span.
            start = 90 * 16
            span = -int(frac * 360 * 16)
            p.drawArc(r, start, span)

        # Centered text — fraction + percent.
        p.setPen(QColor(0, 0, 0))
        f_big = QFont()
        f_big.setPointSize(20); f_big.setBold(True)
        p.setFont(f_big)
        txt = f"{self._done}/{self._total}" if self._total else "—"
        p.drawText(self.rect().adjusted(0, -8, 0, 0),
                   Qt.AlignmentFlag.AlignCenter, txt)
        f_small = QFont()
        f_small.setPointSize(10)
        p.setFont(f_small)
        p.setPen(QColor(120, 120, 120))
        pct = f"{int((self._done / self._total) * 100)}%" if self._total else ""
        p.drawText(self.rect().adjusted(0, 18, 0, 0),
                   Qt.AlignmentFlag.AlignCenter, pct)
        p.end()
