"""First-run wizard — guided install of Homebrew, whisper-cpp, ffmpeg, model.

Shown at startup if `core.deps.check()` reports anything missing. Walks the
user through each step with clear status labels. The heaviest step (model
download ~1.5 GB) runs in a thread with live progress.
"""

from __future__ import annotations

import subprocess
import threading

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import deps
from core.model_download import download_model
from ui.themes import current_tokens
from ui.widgets import Pill


def _make_divider(parent: QWidget) -> QFrame:
    f = QFrame(parent)
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background-color: {current_tokens()['line']};")
    return f


class StepRow(QWidget):
    """One dep row: label (flex) | sub-copy | Pill status | optional action button."""

    def __init__(self, title: str):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(2)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(title)
        self.label.setStyleSheet("font-weight: 500; font-size: 13px;")
        self.pill = Pill("checking…", kind="idle")
        self.action_btn = QPushButton()
        self.action_btn.setVisible(False)
        top.addWidget(self.label, stretch=1)
        top.addWidget(self.pill)
        top.addWidget(self.action_btn)
        outer.addLayout(top)

        self.subcopy = QLabel("")
        self.subcopy.setStyleSheet(f"color: {current_tokens()['ink_3']}; font-size: 11px;")
        self.subcopy.setVisible(False)
        self.subcopy.setWordWrap(True)
        outer.addWidget(self.subcopy)

    # ---- state helpers ---------------------------------------------------
    def _set_sub(self, text: str = "") -> None:
        if text:
            self.subcopy.setText(text)
            self.subcopy.setVisible(True)
        else:
            self.subcopy.clear()
            self.subcopy.setVisible(False)

    def set_ok(self, text: str = "ok") -> None:
        self.pill.setText(text)
        self.pill.set_kind("ok")
        self._set_sub("")
        self.action_btn.setVisible(False)

    def set_missing(self, action_text: str, on_click, reason: str = "not installed") -> None:
        self.pill.setText("fail")
        self.pill.set_kind("fail")
        self._set_sub(reason)
        # Disconnect any prior handlers so re-wiring across refresh() doesn't stack.
        try:
            self.action_btn.clicked.disconnect()
        except TypeError:
            pass
        self.action_btn.setText(action_text)
        self.action_btn.clicked.connect(on_click)
        self.action_btn.setEnabled(True)
        self.action_btn.setVisible(True)

    def set_running(self, text: str = "running…", sub: str = "") -> None:
        self.pill.setText(text)
        self.pill.set_kind("running")
        self._set_sub(sub)
        self.action_btn.setEnabled(False)

    def set_idle(self, sub: str = "") -> None:
        self.pill.setText("checking…")
        self.pill.set_kind("idle")
        self._set_sub(sub)
        self.action_btn.setVisible(False)

    def set_waiting(self, reason: str) -> None:
        """Locked row: predecessor isn't ready yet. No action button."""
        self.pill.setText("waiting")
        self.pill.set_kind("idle")
        self._set_sub(reason)
        self.action_btn.setVisible(False)

    def set_sub_line(self, text: str) -> None:
        """Update only the sub-copy line — lets the brew stdout feed tick
        without disturbing the pill state. Truncates at 80 chars so a very
        long path doesn't blow up the row width."""
        if len(text) > 80:
            text = text[:77] + "…"
        self._set_sub(text)


class FirstRunWizard(QDialog):
    progress_sig = pyqtSignal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paragraphos — First-run setup")
        self.setModal(True)
        self.resize(640, 460)

        v = QVBoxLayout(self)
        v.setSpacing(8)

        heading = QLabel("<h3 style='margin:0'>Welcome to Paragraphos</h3>")
        v.addWidget(heading)
        sub = QLabel(
            "Everything runs locally. We need a few tools on your Mac before the first run."
        )
        sub.setStyleSheet(f"color: {current_tokens()['ink_3']}; font-size: 11px;")
        sub.setWordWrap(True)
        v.addWidget(sub)

        v.addWidget(_make_divider(self))

        self.brew_row = StepRow("Homebrew (package manager)")
        self.whisper_row = StepRow("whisper-cpp (transcription engine)")
        self.ffmpeg_row = StepRow("ffmpeg (audio decoding)")
        self.model_row = StepRow("whisper large-v3-turbo model (~1.5 GB)")

        rows = (self.brew_row, self.whisper_row, self.ffmpeg_row, self.model_row)
        for i, r in enumerate(rows):
            v.addWidget(r)
            if i < len(rows) - 1:
                v.addWidget(_make_divider(self))

        v.addWidget(_make_divider(self))

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        v.addWidget(self.progress)

        v.addStretch()

        footer = QHBoxLayout()
        footer.addStretch()
        # Recheck re-runs the dep scan so users can click it after
        # installing Homebrew in the external Terminal, without having
        # to close + reopen the wizard.
        self.recheck_btn = QPushButton("Recheck")
        self.recheck_btn.clicked.connect(self._on_recheck_clicked)
        footer.addWidget(self.recheck_btn)
        self.close_btn = QPushButton("Continue to Paragraphos")
        self.close_btn.setDefault(True)
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setEnabled(False)
        footer.addWidget(self.close_btn)
        v.addLayout(footer)

        self.progress_sig.connect(self._on_progress)

        # Guard rails: each brew install fires exactly once per wizard session.
        # _refresh can run many times (Recheck button, tick after another install,
        # etc.) — without these flags it would spawn overlapping `brew install`
        # invocations, and brew holds a global lock so the second call fails.
        self._whisper_started = False
        self._ffmpeg_started = False
        self._model_started = False

        QTimer.singleShot(0, self._refresh)

    def _on_recheck_clicked(self) -> None:
        """Recheck with visible feedback — flashes the button text so the
        user sees the click registered, and includes a tooltip with the
        detected dep paths so they can tell what's failing."""
        self.recheck_btn.setText("Rechecking…")
        self.recheck_btn.setEnabled(False)

        def run_check():
            status = deps.check()
            # Build tooltip string for debugging
            parts = [
                f"brew: {'✓' if status.brew else '✗'}",
                f"whisper-cli: {'✓' if status.whisper_cli else '✗'}",
                f"ffmpeg: {'✓' if status.ffmpeg else '✗'}",
                f"model: {'✓' if status.model else '✗'}",
            ]
            self.recheck_btn.setToolTip(" · ".join(parts))
            self.recheck_btn.setText("Recheck")
            self.recheck_btn.setEnabled(True)
            self._refresh()

        QTimer.singleShot(250, run_check)

    # ---- refresh --------------------------------------------------------
    def _refresh(self):
        status = deps.check()
        if status.brew:
            self.brew_row.set_ok()
        else:
            self.brew_row.set_missing(
                "Install Homebrew…",
                self._install_brew,
                reason="Homebrew is not installed on this Mac.",
            )
        if status.whisper_cli:
            self.whisper_row.set_ok()
        elif status.brew:
            if not self._whisper_started:
                self._whisper_started = True
                self._install_whisper()
            # If already running, _install_whisper has set the row's state; leave as-is.
        else:
            self.whisper_row.set_waiting("waiting for Homebrew")
        if status.ffmpeg:
            self.ffmpeg_row.set_ok()
        elif status.brew and status.whisper_cli:
            if not self._ffmpeg_started:
                self._ffmpeg_started = True
                self._install_ffmpeg()
        elif status.brew:
            self.ffmpeg_row.set_waiting("waiting for whisper-cpp to finish")
        else:
            self.ffmpeg_row.set_waiting("waiting for Homebrew")
        if status.model:
            self.model_row.set_ok()
        elif not self._model_started:
            self._model_started = True
            self._download_model()
        # else: already downloading; _download_model has set row state.
        # Gate Continue on the full four-check set.
        all_ok = status.brew and status.whisper_cli and status.ffmpeg and status.model
        self.close_btn.setEnabled(all_ok)

    def _install_brew(self):
        """Homebrew's installer needs an interactive Terminal (sudo). Write
        a throwaway .command script and ``open`` it — macOS launches
        Terminal.app and runs the script there. More reliable than
        ``osascript tell Terminal to do script`` which silently fails
        when the brew one-liner has embedded quotes / $() and when
        Automation permission hasn't been granted.
        """
        import os
        import tempfile

        from PyQt6.QtWidgets import QMessageBox

        cmd = deps.install_brew_command()
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".command",
            prefix="paragraphos-install-brew-",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write("#!/bin/sh\n")
            f.write("set -e\n")
            f.write(cmd + "\n")
            f.write('\necho ""\n')
            f.write(
                'echo "✓ Homebrew installer finished. Close this window and '
                'click Recheck in Paragraphos."\n'
            )
            script_path = f.name
        os.chmod(script_path, 0o755)
        try:
            subprocess.Popen(["open", "-a", "Terminal", script_path])
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Couldn't open Terminal",
                f"Could not launch Terminal.app: {exc}\n\n"
                f"Run this manually in a Terminal, then click Recheck:\n\n{cmd}",
            )
            return
        QMessageBox.information(
            self,
            "Homebrew installer opened",
            "A Terminal window opened with the Homebrew installer. "
            "Finish the install there (you will be asked for your password), "
            "then click OK to recheck.",
        )
        self._refresh()

    def _install_whisper(self):
        self.whisper_row.set_running("installing…", sub="brew install whisper-cpp…")

        def run():
            p = deps.install_whisper_cpp()
            msg = "" if p.returncode == 0 else p.stderr[-200:]
            QTimer.singleShot(0, lambda: self._after_cli(self.whisper_row, p.returncode == 0, msg))

        threading.Thread(target=run, daemon=True).start()

    def _install_ffmpeg(self):
        self.ffmpeg_row.set_running("installing…", sub="brew install ffmpeg…")

        def run():
            p = deps.install_ffmpeg()
            msg = "" if p.returncode == 0 else p.stderr[-200:]
            QTimer.singleShot(0, lambda: self._after_cli(self.ffmpeg_row, p.returncode == 0, msg))

        threading.Thread(target=run, daemon=True).start()

    def _after_cli(self, row: "StepRow", ok: bool, err: str) -> None:
        if ok:
            row.set_ok()
            self._refresh()
            return
        # Fail path — reset the guard for this install and re-attach a
        # retry action so the user isn't stuck. Map the row back to the
        # started-flag + install callable.
        if row is self.whisper_row:
            self._whisper_started = False
            retry_fn = self._install_whisper
        elif row is self.ffmpeg_row:
            self._ffmpeg_started = False
            retry_fn = self._install_ffmpeg
        elif row is self.model_row:
            self._model_started = False
            retry_fn = self._download_model
        else:
            retry_fn = None
        reason = err[:160] if err else "install failed"
        if retry_fn is not None:
            row.set_missing("Retry", retry_fn, reason=reason)
        else:
            row.pill.setText("fail")
            row.pill.set_kind("fail")
            row._set_sub(reason)
        # Intentionally skip _refresh on fail: it would re-trigger the install
        # (flag just reset) and overwrite the Retry button with set_running.
        # The Continue button stays disabled because deps are still missing.
        self.close_btn.setEnabled(False)

    def _download_model(self):
        self.model_row.set_running("downloading…", sub="fetching model file…")
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)

        def run():
            def on_prog(done: int, total: int):
                self.progress_sig.emit("model", done, total)

            try:
                download_model("large-v3-turbo", on_prog)
                QTimer.singleShot(0, lambda: (self.progress.setVisible(False), self._refresh()))
            except Exception as e:
                QTimer.singleShot(0, lambda e=e: self._after_cli(self.model_row, False, str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, kind: str, done: int, total: int):
        if total:
            self.progress.setValue(int(done * 100 / total))
        self.model_row._set_sub(f"downloading… {done // (1024 * 1024)} MB")


def show_wizard_if_needed(app) -> bool:
    """Returns True if user should proceed to main window (deps OK or completed)."""
    if deps.check().all_ok:
        return True
    dlg = FirstRunWizard()
    return dlg.exec() == QDialog.DialogCode.Accepted
