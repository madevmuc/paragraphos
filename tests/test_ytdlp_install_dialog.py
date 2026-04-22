import os
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication


def _pump_until(app, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def test_install_dialog_runs_install_and_emits_done(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)

    from ui.ytdlp_install_dialog import YtdlpInstallDialog

    def fake_install(progress=None):
        if progress:
            progress(50, 100)
            progress(100, 100)
        (tmp_path / "bin").mkdir(parents=True)
        (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")

    results: list[bool] = []

    with patch("core.ytdlp.install", side_effect=fake_install):
        dlg = YtdlpInstallDialog(mode="install")
        dlg.finished_install.connect(results.append)
        dlg.start()
        _pump_until(app, lambda: bool(results), timeout=3.0)

    assert results == [True]
