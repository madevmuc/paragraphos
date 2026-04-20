"""Render the tray icon as a live `done/total` fraction during a run.

Idle: `P` glyph. Running: draws `3/12` (or current counter) into a
22×22 / 44×44 pixmap via QPainter. Dark-mode detection via
QApplication.palette().windowText() lightness.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication


class IconRenderer:
    def __init__(self, base_size: int = 22):
        self._base = base_size

    def _fg(self) -> QColor:
        # On macOS the menu-bar icon tints against the current appearance.
        # Use palette windowText lightness as a proxy; dark text in light
        # mode, light text in dark mode.
        app = QApplication.instance()
        if app is None:
            return QColor(30, 30, 30)
        c = app.palette().windowText().color()
        return c

    def _draw(self, text: str, pm: QPixmap) -> None:
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self._fg())
        f = QFont()
        # Small fractions fit better than large ones on macOS menu bar.
        f.setPointSize(10 if len(text) > 2 else 14)
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
        p.end()

    def render(
        self,
        done: int = 0,
        total: int = 0,
        running: bool = False,
        override_text: Optional[str] = None,
    ) -> QIcon:
        if override_text is not None:
            text = override_text
        elif running and total > 0:
            text = f"{done}/{total}"
        else:
            text = "P"

        pm1 = QPixmap(self._base, self._base)
        self._draw(text, pm1)
        pm2 = QPixmap(self._base * 2, self._base * 2)
        self._draw(text, pm2)

        icon = QIcon(pm1)
        icon.addPixmap(pm2)
        return icon
