"""Render the tray icon — painter-drawn glyph as a macOS template image.

macOS treats menu-bar icons specially: only icons marked as template
images (NSImage.isTemplate / QIcon.setIsMask(True)) get the system's
correct sizing, auto-tinting for light/dark + accent colours, and
priority placement (don't get hidden behind the macOS 26 menu-bar
overflow chevron). The renderer therefore draws the glyph as a black-
on-transparent ALPHA MASK and flips the resulting QIcon to mask mode;
macOS auto-tints from the alpha shape.

Idle: bold "P" filling the canvas. Running: live "3/12" fraction.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap


class IconRenderer:
    def __init__(self, base_size: int = 22):
        self._base = base_size

    def _draw(self, text: str, pm: QPixmap) -> None:
        # Template images on macOS are alpha-only — the OS ignores pen
        # colour and only uses the alpha shape. Draw in opaque black so
        # the glyph silhouette becomes the alpha mask exactly.
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(QColor(0, 0, 0, 255))
        f = QFont()
        # Single-glyph idle ("P") wants a big point size so it fills the
        # menu-bar canvas; multi-char fractions ("12/40") need to fit too.
        f.setPointSize(11 if len(text) > 2 else 16)
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

        # 1× (22 px) for non-Retina + 2× (44 px) for Retina menu bars.
        pm1 = QPixmap(self._base, self._base)
        pm1.setDevicePixelRatio(1.0)
        self._draw(text, pm1)
        pm2 = QPixmap(self._base * 2, self._base * 2)
        pm2.setDevicePixelRatio(2.0)
        self._draw(text, pm2)

        icon = QIcon(pm1)
        icon.addPixmap(pm2)
        # macOS template image — system handles tint + sizing + overflow.
        icon.setIsMask(True)
        return icon
