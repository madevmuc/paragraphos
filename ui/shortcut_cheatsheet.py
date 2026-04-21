"""Read-only keyboard shortcut cheatsheet overlay.

Harvests shortcuts at display time from the main window's QMenuBar so it
stays in sync with `ui/menu_bar.py`. Window-scoped QShortcuts (registered in
`ui/main_window.py`) aren't QActions on the menu, so they're surfaced as a
manual "Navigation" section.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# Window-scoped QShortcut bindings mirrored from ui/main_window.py:144-152.
# These are real shortcuts but not QActions on the menu bar, so we can't
# harvest them; list them manually here and keep this in sync by eye.
_NAVIGATION_MANUAL: list[tuple[str, str]] = [
    ("?", "Show this cheatsheet"),
    ("Ctrl+/", "Show this cheatsheet"),
]


class ShortcutCheatsheet(QDialog):
    """Modal-ish overlay listing every known shortcut, grouped by menu."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setModal(False)
        self.resize(520, 520)

        self._sections: list[tuple[str, list[tuple[str, str]]]] = self._harvest(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(8)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        for title, rows in self._sections:
            if not rows:
                continue
            header = QLabel(title)
            header.setStyleSheet("font-weight: 600; font-size: 13px;")
            v.addWidget(header)
            for shortcut, action in rows:
                v.addWidget(_row(shortcut, action))
            v.addSpacing(4)
        v.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        hint = QLabel("Press Esc or ? to close.")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        hint.setStyleSheet("color: palette(mid); font-size: 11px;")
        outer.addWidget(hint)

    # ── public helpers used by the verify script ───────────────────

    def total_rows(self) -> int:
        return sum(len(rows) for _, rows in self._sections)

    def rowCount_by_section(self) -> dict[str, int]:
        return {title: len(rows) for title, rows in self._sections}

    # ── harvesting ─────────────────────────────────────────────────

    @staticmethod
    def _harvest(window) -> list[tuple[str, list[tuple[str, str]]]]:
        sections: list[tuple[str, list[tuple[str, str]]]] = []
        # 1) Manual Navigation section for window-scoped QShortcuts.
        sections.append(("Navigation", list(_NAVIGATION_MANUAL)))

        # 2) Harvest every QAction with a non-empty shortcut from the menu
        #    bar, grouped by enclosing QMenu title.
        if window is None:
            return sections
        mb = window.menuBar() if hasattr(window, "menuBar") else None
        if mb is None:
            return sections

        for menu in mb.findChildren(QMenu):
            # Skip nested/sub-orphan menus with no title.
            title = menu.title().replace("&", "").strip()
            if not title:
                continue
            rows: list[tuple[str, str]] = []
            for act in menu.actions():
                if not isinstance(act, QAction):
                    continue
                if act.isSeparator() or act.menu() is not None:
                    continue
                seq: QKeySequence = act.shortcut()
                if seq.isEmpty():
                    continue
                label = act.text().replace("&", "").strip()
                if not label:
                    continue
                rows.append((seq.toString(QKeySequence.SequenceFormat.NativeText), label))
            if rows:
                sections.append((title, rows))
        return sections

    # ── key handling ───────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.key() == Qt.Key.Key_Escape or event.key() == Qt.Key.Key_Question:
            self.close()
            return
        super().keyPressEvent(event)


def _row(shortcut: str, action: str) -> QWidget:
    w = QWidget()
    from PyQt6.QtWidgets import QHBoxLayout

    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)

    sc = QLabel(shortcut)
    sc.setFixedWidth(110)
    sc.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    sc.setStyleSheet("font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 12px;")
    h.addWidget(sc)

    lbl = QLabel(action)
    lbl.setStyleSheet("font-size: 13px;")
    h.addWidget(lbl, stretch=1)
    return w
