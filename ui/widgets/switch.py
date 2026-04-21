"""Compact iOS-style toggle switch — custom QAbstractButton.

Qt doesn't ship a switch widget; QCheckBox renders as a square box on
macOS. This paints the familiar capsule-with-thumb used across the
rest of the OS. Emits ``toggled(bool)`` like a checkbox, so it's a
drop-in replacement for any on/off flag.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter
from PyQt6.QtWidgets import QAbstractButton


class Switch(QAbstractButton):
    def __init__(self, parent=None, *, width: int = 38, height: int = 22):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self) -> QSize:  # noqa: N802 — Qt override
        return self.size()

    def paintEvent(self, _ev) -> None:  # noqa: N802 — Qt override
        # Defensive try/except: any Python exception bubbling out of a
        # PyQt paintEvent hits qFatal → abort (SIGABRT) and kills the
        # whole app — we'd rather silently skip a frame than crash.
        try:
            self._paint()
        except Exception:
            pass

    def _paint(self) -> None:
        w = float(self.width())
        h = float(self.height())
        radius = h / 2.0

        # Colours from the theme tokens. Defensive fallback keeps the
        # widget paintable even before the ThemeManager is installed.
        try:
            from ui.themes import current_tokens

            t = current_tokens()
            on_col = QColor(t.get("accent") or "#b47a3a")
            off_col = QColor(t.get("line") or "#d8d4cb")
        except Exception:
            on_col = QColor("#34c759")
            off_col = QColor("#888888")
        thumb_col = QColor("#ffffff")

        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(Qt.PenStyle.NoPen)

            # Track
            p.setBrush(QBrush(on_col if self.isChecked() else off_col))
            p.drawRoundedRect(QRectF(0.0, 0.0, w, h), radius, radius)

            # Thumb
            d = h - 4.0
            x = (w - d - 2.0) if self.isChecked() else 2.0
            p.setBrush(QBrush(thumb_col))
            p.drawEllipse(QRectF(x, 2.0, d, d))
        finally:
            p.end()
