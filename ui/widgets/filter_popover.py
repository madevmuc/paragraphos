"""Popover anchored to a button — shows filter checkboxes."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class FilterPopover(QDialog):
    """Frameless popup for the Shows-tab filters.

    Emits `applied(state)` where `state` is a dict:
      {enabled_only, has_pending, has_failed,
       feed_ok, feed_stale, feed_unreachable, search}
    """

    applied = pyqtSignal(dict)

    def __init__(self, initial: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setFixedWidth(220)
        state = initial or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        self.cb_enabled = QCheckBox("Enabled only")
        self.cb_pending = QCheckBox("Has pending episodes")
        self.cb_failed = QCheckBox("Has failed episodes")
        for cb, key in (
            (self.cb_enabled, "enabled_only"),
            (self.cb_pending, "has_pending"),
            (self.cb_failed, "has_failed"),
        ):
            cb.setChecked(bool(state.get(key, False)))
            root.addWidget(cb)

        lbl = QLabel("FEED STATUS")
        lbl.setProperty("class", "mini-label")
        root.addWidget(lbl)
        self.cb_ok = QCheckBox("✅ ok")
        self.cb_stale = QCheckBox("⚠ stale")
        self.cb_unreach = QCheckBox("✖ unreachable")
        for cb, key in (
            (self.cb_ok, "feed_ok"),
            (self.cb_stale, "feed_stale"),
            (self.cb_unreach, "feed_unreachable"),
        ):
            cb.setChecked(bool(state.get(key, False)))
            root.addWidget(cb)

        lbl2 = QLabel("SEARCH")
        lbl2.setProperty("class", "mini-label")
        root.addWidget(lbl2)
        self.search = QLineEdit()
        self.search.setText(state.get("search", ""))
        root.addWidget(self.search)

        btns = QHBoxLayout()
        clear = QPushButton("Clear")
        clear.setProperty("role", "ghost")
        clear.clicked.connect(self._clear)
        apply = QPushButton("Apply")
        apply.setProperty("role", "primary")
        apply.clicked.connect(self._apply)
        btns.addStretch()
        btns.addWidget(clear)
        btns.addWidget(apply)
        root.addLayout(btns)

    def _clear(self):
        for cb in (
            self.cb_enabled,
            self.cb_pending,
            self.cb_failed,
            self.cb_ok,
            self.cb_stale,
            self.cb_unreach,
        ):
            cb.setChecked(False)
        self.search.clear()

    def _apply(self):
        self.applied.emit(
            {
                "enabled_only": self.cb_enabled.isChecked(),
                "has_pending": self.cb_pending.isChecked(),
                "has_failed": self.cb_failed.isChecked(),
                "feed_ok": self.cb_ok.isChecked(),
                "feed_stale": self.cb_stale.isChecked(),
                "feed_unreachable": self.cb_unreach.isChecked(),
                "search": self.search.text().strip(),
            }
        )
        self.accept()

    def show_at_button(self, button):
        """Anchor the popover just below the clicked button."""
        pos = button.mapToGlobal(button.rect().bottomLeft())
        self.move(pos.x(), pos.y() + 4)
        self.show()
