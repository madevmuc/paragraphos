"""Log dock widget — receives progress strings from worker threads."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtWidgets import QDockWidget, QPlainTextEdit


class LogDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Log", parent)
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(2000)
        self._text.setStyleSheet("font-family: Menlo, Monaco, monospace; font-size: 11px;")
        self.setWidget(self._text)

    def append(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._text.appendPlainText(f"{ts}  {msg}")
