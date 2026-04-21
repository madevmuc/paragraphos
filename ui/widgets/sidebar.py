"""Vertical navigation sidebar — replaces the top `QTabWidget`."""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class _SidebarItem(QFrame):
    """One clickable row: label on the left, count chip on the right."""

    clicked = pyqtSignal(str)

    def __init__(self, key: str, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SidebarItem")
        self._key = key
        self._label = QLabel(label)
        self._count = QLabel("")
        self._count.setProperty("class", "count")
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self._label)
        h.addStretch()
        h.addWidget(self._count)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("active", False)

    def mousePressEvent(self, ev) -> None:
        self.clicked.emit(self._key)

    def set_count(self, n: int | str) -> None:
        self._count.setText(str(n) if n else "")

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """Emits `navigate(key)` when the user clicks an item."""

    navigate = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(160)
        self._items: dict[str, _SidebarItem] = {}
        self._active: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(2)
        self._layout = layout

    def add_group(self, title: str) -> None:
        lbl = QLabel(title)
        lbl.setProperty("class", "mini-label")
        lbl.setContentsMargins(0, 10, 0, 4)
        self._layout.addWidget(lbl)

    def add_item(self, key: str, label: str) -> None:
        it = _SidebarItem(key, label)
        it.clicked.connect(self._on_item_clicked)
        self._items[key] = it
        self._layout.addWidget(it)

    def finish(self) -> None:
        self._layout.addStretch()

    def _on_item_clicked(self, key: str) -> None:
        self.set_active(key)
        self.navigate.emit(key)

    def set_active(self, key: str) -> None:
        self._active = key
        for k, it in self._items.items():
            it.set_active(k == key)

    def set_count(self, key: str, n: int | str) -> None:
        if key in self._items:
            self._items[key].set_count(n)
