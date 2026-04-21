"""Render the tray icon — static template when idle, live fraction when running.

Idle: `assets/MenuBarIconTemplate.png` loaded as a macOS template image
(`setIsMask(True)`) so macOS auto-tints to match the menu bar.
Running: draws `3/12` (or current counter) into a 22×22 / 44×44 pixmap via
QPainter — source of truth for color is `QGuiApplication.styleHints()
.colorScheme()`, per the icon handoff.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPixmap

_ASSETS = Path(__file__).resolve().parent.parent.parent / "assets"


def _load_template_icon() -> Optional[QIcon]:
    """Return the bundled template icon (mask=True) or None if missing."""
    base = _ASSETS / "MenuBarIconTemplate.png"
    if not base.exists():
        return None
    icon = QIcon()
    # Register 1x, 2x, 3x if available so HiDPI menu bars get crisp scaling.
    for name in (
        "MenuBarIconTemplate.png",
        "MenuBarIconTemplate_2x.png",
        "MenuBarIconTemplate_3x.png",
    ):
        p = _ASSETS / name
        if p.exists():
            icon.addFile(str(p))
    icon.setIsMask(True)  # macOS NSImage.isTemplate = YES equivalent
    return icon


class IconRenderer:
    def __init__(self, base_size: int = 22):
        self._base = base_size
        self._template: Optional[QIcon] = _load_template_icon()

    def _fg(self) -> QColor:
        """Near-black on a light menu bar, near-white on a dark one.

        Uses `styleHints().colorScheme()` — the menu bar always follows
        the system appearance even if individual apps force a theme
        override. Values from handoff lines 162–164.
        """
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return QColor(0xEC, 0xEC, 0xEC)
        return QColor(0x1A, 0x1A, 0x1A)

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
            # Idle: prefer the bundled template (macOS auto-tints) over the
            # painter glyph. Falls back to "P" if the template isn't bundled.
            if self._template is not None:
                return self._template
            text = "P"

        pm1 = QPixmap(self._base, self._base)
        self._draw(text, pm1)
        pm2 = QPixmap(self._base * 2, self._base * 2)
        self._draw(text, pm2)

        icon = QIcon(pm1)
        icon.addPixmap(pm2)
        return icon
