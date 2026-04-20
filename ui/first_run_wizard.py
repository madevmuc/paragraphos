"""First-run wizard — guided install of Homebrew, whisper-cpp, ffmpeg, model.

Shown at startup if `core.deps.check()` reports anything missing. Walks the
user through each step with clear status labels. The heaviest step (model
download ~1.5 GB) runs in a thread with live progress.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel,
                             QProgressBar, QPushButton, QVBoxLayout, QWidget)

from core import deps
from core.model_download import AVAILABLE as MODEL_FILES
from core.model_download import download_model


class StepRow(QWidget):
    def __init__(self, title: str):
        super().__init__()
        h = QHBoxLayout(self)
        self.label = QLabel(title)
        self.status = QLabel("⏳ checking…")
        self.action_btn = QPushButton()
        self.action_btn.setVisible(False)
        h.addWidget(self.label)
        h.addWidget(self.status, stretch=1)
        h.addWidget(self.action_btn)

    def set_ok(self, text: str = "✓ installed"):
        self.status.setText(text)
        self.status.setStyleSheet("color:#5a8a4a;")
        self.action_btn.setVisible(False)

    def set_missing(self, action_text: str, on_click):
        self.status.setText("not installed")
        self.status.setStyleSheet("color:#a06030;")
        self.action_btn.setText(action_text)
        self.action_btn.clicked.connect(on_click)
        self.action_btn.setVisible(True)

    def set_running(self, text: str = "running…"):
        self.status.setText(text)
        self.status.setStyleSheet("color:#606090;")
        self.action_btn.setEnabled(False)


class FirstRunWizard(QDialog):
    progress_sig = pyqtSignal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paragraphos — First-run setup")
        self.setModal(True)
        self.resize(640, 420)

        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            "<h3>Welcome to Paragraphos</h3>"
            "Paragraphos runs everything locally — no cloud services. We need a "
            "few tools on your Mac before the first run:"))

        self.brew_row = StepRow("Homebrew (package manager)")
        self.whisper_row = StepRow("whisper-cpp (transcription engine)")
        self.ffmpeg_row = StepRow("ffmpeg (audio decoding)")
        self.model_row = StepRow("whisper large-v3-turbo model (~1.5 GB)")
        for r in (self.brew_row, self.whisper_row, self.ffmpeg_row, self.model_row):
            v.addWidget(r)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        v.addWidget(self.progress)

        self.close_btn = QPushButton("Continue to Paragraphos")
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setEnabled(False)
        v.addStretch()
        v.addWidget(self.close_btn)

        self.progress_sig.connect(self._on_progress)
        QTimer.singleShot(0, self._refresh)

    def _refresh(self):
        status = deps.check()
        if status.brew:
            self.brew_row.set_ok()
        else:
            self.brew_row.set_missing("Install Homebrew…", self._install_brew)
        if status.whisper_cli:
            self.whisper_row.set_ok()
        elif status.brew:
            self.whisper_row.set_missing("brew install", self._install_whisper)
        else:
            self.whisper_row.status.setText("waiting for Homebrew")
        if status.ffmpeg:
            self.ffmpeg_row.set_ok()
        elif status.brew:
            self.ffmpeg_row.set_missing("brew install", self._install_ffmpeg)
        else:
            self.ffmpeg_row.status.setText("waiting for Homebrew")
        if status.model:
            self.model_row.set_ok()
        else:
            self.model_row.set_missing("Download…", self._download_model)
        self.close_btn.setEnabled(status.all_ok)

    def _install_brew(self):
        """Homebrew's installer needs an interactive Terminal (sudo). Open
        Terminal.app with the prefilled command — user authenticates there,
        then returns here and clicks 'Recheck'."""
        from PyQt6.QtWidgets import QMessageBox
        cmd = deps.install_brew_command()
        subprocess.run(["osascript", "-e",
                        f'tell application "Terminal" to do script "{cmd}"'])
        QMessageBox.information(
            self, "Homebrew installer opened",
            "A Terminal window opened with the Homebrew installer. "
            "Finish the install there (you will be asked for your password), "
            "then click OK to recheck.")
        self._refresh()

    def _install_whisper(self):
        self.whisper_row.set_running("brew install whisper-cpp…")

        def run():
            p = deps.install_whisper_cpp()
            msg = "" if p.returncode == 0 else p.stderr[-200:]
            QTimer.singleShot(0, lambda: self._after_cli(self.whisper_row, p.returncode == 0, msg))
        threading.Thread(target=run, daemon=True).start()

    def _install_ffmpeg(self):
        self.ffmpeg_row.set_running("brew install ffmpeg…")

        def run():
            p = deps.install_ffmpeg()
            msg = "" if p.returncode == 0 else p.stderr[-200:]
            QTimer.singleShot(0, lambda: self._after_cli(self.ffmpeg_row, p.returncode == 0, msg))
        threading.Thread(target=run, daemon=True).start()

    def _after_cli(self, row: StepRow, ok: bool, err: str):
        if ok:
            row.set_ok()
        else:
            row.status.setText(f"✖ {err[:80]}")
            row.status.setStyleSheet("color:#a04040;")
        self._refresh()

    def _download_model(self):
        self.model_row.set_running("downloading…")
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)

        def run():
            def on_prog(done: int, total: int):
                self.progress_sig.emit("model", done, total)
            try:
                download_model("large-v3-turbo", on_prog)
                QTimer.singleShot(0, lambda: (self.progress.setVisible(False),
                                              self._refresh()))
            except Exception as e:
                QTimer.singleShot(0, lambda: self._after_cli(
                    self.model_row, False, str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, kind: str, done: int, total: int):
        if total:
            self.progress.setValue(int(done * 100 / total))
        self.model_row.status.setText(f"downloading… {done // (1024*1024)} MB")


def show_wizard_if_needed(app) -> bool:
    """Returns True if user should proceed to main window (deps OK or completed)."""
    if deps.check().all_ok:
        return True
    dlg = FirstRunWizard()
    return dlg.exec() == QDialog.DialogCode.Accepted
