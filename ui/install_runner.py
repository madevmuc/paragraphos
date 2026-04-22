"""Run ``brew install <pkg>`` and stream its stdout line-by-line to Qt signals.

The wizard uses this so users see live output during installs instead of a
silent "installing…" pill. A daemon reader thread pulls lines off the child's
stdout and emits a Qt signal; the Qt event loop delivers them on the GUI
thread where widgets can be updated safely.
"""

from __future__ import annotations

import subprocess
import threading
from typing import Sequence

from PyQt6.QtCore import QObject, pyqtSignal

from core.deps import _brew_env


class BrewRunner(QObject):
    line = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, cmd: Sequence[str], parent: QObject | None = None):
        super().__init__(parent)
        self._cmd = list(cmd)
        self._proc: subprocess.Popen[str] | None = None

    def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError("BrewRunner.start() called twice on the same instance")
        self._proc = subprocess.Popen(
            self._cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=_brew_env(),
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        code = -1
        try:
            for raw in self._proc.stdout:
                line = raw.rstrip("\n")
                if line:
                    self.line.emit(line)
            code = self._proc.wait()
        finally:
            if self._proc.stdout is not None:
                self._proc.stdout.close()
            self.finished.emit(code)
