"""Log dock widget — receives progress strings from worker threads.

Click the title bar to copy the full buffer to the clipboard (handy for
pasting into bug reports).
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)


class _CopyOnClickTitle(QLabel):
    """Title-bar label that copies the parent dock's text on click."""

    def __init__(self, dock: "LogDock") -> None:
        super().__init__("Log  (click to copy)")
        self._dock = dock
        self.setStyleSheet("padding: 4px 8px; font-weight: 600;")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._dock.copy_all()
            QToolTip.showText(
                ev.globalPosition().toPoint(),
                "Log copied to clipboard",
                self,
            )
        super().mousePressEvent(ev)


class LogDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Log", parent)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        self._text.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px;")
        self.setWidget(self._text)
        # Replace the default title bar with a clickable label so users can
        # one-click copy the buffer for bug reports.
        self.setTitleBarWidget(_CopyOnClickTitle(self))

    def append(self, msg: str) -> None:
        # Full date + time so a long-running session's log entries stay
        # unambiguous (an `08:23:14` could be from this morning or
        # yesterday — the in-app dock didn't carry the day before).
        # Matches the file-handler's `YYYY-MM-DD HH:MM:SS` so copying
        # from the dock and grepping the on-disk log line up.
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._text.appendPlainText(f"{ts}  {msg}")

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self._text.toPlainText())


class LogsPane(QWidget):
    """Full-window log pane — shown when the user picks "Logs" in the
    sidebar. Shares the append API with LogDock: `MainWindow` fans every
    log message into both so toggling between pane and dock never drops
    entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        header = QHBoxLayout()
        header.addStretch(1)
        copy_btn = QPushButton("Copy log")
        copy_btn.clicked.connect(self.copy_all)
        header.addWidget(copy_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        v.addLayout(header)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        self._text.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px;")
        v.addWidget(self._text, 1)

    def append(self, msg: str) -> None:
        # Full date + time so a long-running session's log entries stay
        # unambiguous (an `08:23:14` could be from this morning or
        # yesterday — the in-app dock didn't carry the day before).
        # Matches the file-handler's `YYYY-MM-DD HH:MM:SS` so copying
        # from the dock and grepping the on-disk log line up.
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._text.appendPlainText(f"{ts}  {msg}")

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self._text.toPlainText())

    def _clear(self) -> None:
        self._text.clear()
