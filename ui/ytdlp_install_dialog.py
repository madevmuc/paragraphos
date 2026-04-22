"""Modal dialog that installs or self-updates yt-dlp on a worker thread."""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)

from core import ytdlp


class _Worker(QObject):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(bool, str)  # success, message

    def __init__(self, mode: Literal["install", "update"]) -> None:
        super().__init__()
        self.mode = mode

    def run(self) -> None:
        try:
            if self.mode == "install":
                ytdlp.install(progress=lambda d, t: self.progress.emit(d, t))
            else:
                ytdlp.self_update()
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))


class YtdlpInstallDialog(QDialog):
    finished_install = pyqtSignal(bool)  # True on success

    def __init__(self, mode: Literal["install", "update"] = "install", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Installing yt-dlp" if mode == "install" else "Updating yt-dlp")
        self._mode = mode
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Downloading yt-dlp so Paragraphos can fetch YouTube videos…"
                if mode == "install"
                else "Updating yt-dlp to keep YouTube downloads working…"
            )
        )
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def start(self) -> None:
        self._thread = QThread(self)
        self._worker = _Worker(self._mode)
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._bar.setValue(int(100 * done / total))

    def _on_done(self, success: bool, message: str) -> None:
        self._thread.quit()
        self._thread.wait()
        self.finished_install.emit(success)
        if success:
            self.accept()
        else:
            self._bar.setFormat(f"Failed: {message}")
            self._buttons.setStandardButtons(QDialogButtonBox.StandardButton.Close)
