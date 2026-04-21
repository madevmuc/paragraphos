"""Compact iOS-style toggle switch — custom QAbstractButton.

Qt doesn't ship a switch widget; QCheckBox renders as a square box on
macOS. This paints the familiar capsule-with-thumb used across the
rest of the OS. Emits ``toggled(bool)`` like a checkbox, so it's a
drop-in replacement for any on/off flag.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath
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
        w, h = self.width(), self.height()
        radius = h // 2
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Track colour — accent when on, mid-grey when off. Reads theme
        # tokens so dark-mode inherits the purple accent automatically.
        try:
            from ui.themes import current_tokens

            t = current_tokens()
            on_col = QColor(t.get("accent", "#b47a3a"))
            off_col = QColor(t.get("line", "#d8d4cb"))
            thumb_col = QColor("#ffffff")
        except Exception:
            on_col, off_col, thumb_col = (
                QColor("#34c759"),
                QColor("#888888"),
                QColor("#ffffff"),
            )

        track = QPainterPath()
        track.addRoundedRect(0, 0, w, h, radius, radius)
        p.fillPath(track, QBrush(on_col if self.isChecked() else off_col))

        # Thumb — fills h-4px, travels track width minus diameter.
        d = h - 4
        x = (w - d - 2) if self.isChecked() else 2
        thumb = QPainterPath()
        thumb.addEllipse(QRect(QPoint(int(x), 2), QSize(d, d)))
        # Soft shadow for depth.
        p.fillPath(thumb.translated(0, 1), QBrush(QColor(0, 0, 0, 40)))
        p.fillPath(thumb, QBrush(thumb_col))
        p.end()
