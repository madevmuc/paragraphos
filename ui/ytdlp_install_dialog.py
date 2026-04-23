"""Modal dialog that installs or self-updates yt-dlp on a worker thread."""

from __future__ import annotations

import time
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
        self.setMinimumWidth(420)
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

        self.progress_label = QLabel("Starting…")
        self.progress_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.progress_label)

        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._started_at: float | None = None
        self._auto_started = False

    def showEvent(self, ev):  # noqa: N802 (Qt API)
        super().showEvent(ev)
        if not self._auto_started:
            self._auto_started = True
            self.start()

    def start(self) -> None:
        # Idempotent: if a worker thread already exists, don't spawn another.
        if getattr(self, "_thread", None) is not None:
            return
        self._auto_started = True
        self._started_at = time.monotonic()
        self._thread = QThread(self)
        self._worker = _Worker(self._mode)
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        pct = int(100 * done / total) if total > 0 else 0
        self._bar.setValue(pct)
        done_mb = done / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        eta_str = self._eta_str(done, total)
        self.progress_label.setText(f"{done_mb:.1f} MB / {total_mb:.1f} MB · {pct}%{eta_str}")

    def _eta_str(self, done: int, total: int) -> str:
        if not (done and total and self._started_at):
            return ""
        elapsed = time.monotonic() - self._started_at
        if elapsed < 0.5 or done >= total:
            return ""
        speed = done / elapsed  # bytes/sec
        if speed <= 0:
            return ""
        remaining = (total - done) / speed
        if remaining > 60:
            return f"  ·  ~{int(remaining // 60)}m {int(remaining % 60)}s remaining"
        return f"  ·  ~{int(remaining)}s remaining"

    def _on_done(self, success: bool, message: str) -> None:
        self._thread.quit()
        self._thread.wait()
        self.finished_install.emit(success)
        if success:
            self.accept()
        else:
            self._bar.setFormat(f"Failed: {message}")
            self._buttons.setStandardButtons(QDialogButtonBox.StandardButton.Close)
