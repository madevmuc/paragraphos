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


def test_progress_label_shows_mb_and_eta(tmp_path, monkeypatch):
    """When install reports 1MB/2MB, the dialog shows MB counters + %."""
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)

    from ui.ytdlp_install_dialog import YtdlpInstallDialog

    dlg = YtdlpInstallDialog(mode="install")
    # Bypass the worker thread; drive _on_progress directly.
    dlg._on_progress(1_048_576, 2_097_152)  # 1 MB / 2 MB
    app.processEvents()
    txt = dlg.progress_label.text()
    assert "1.0" in txt and "2.0" in txt and "MB" in txt
    assert "50%" in txt or "50 %" in txt


def test_dialog_auto_starts_install_on_show(tmp_path, monkeypatch):
    """show() should kick off the worker without an extra start() call."""
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    started = {"called": False}

    def fake_install(progress=None):
        started["called"] = True
        if progress:
            progress(100, 100)
        (tmp_path / "bin").mkdir(parents=True)
        (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")

    results: list[bool] = []

    with patch("core.ytdlp.install", side_effect=fake_install):
        from ui.ytdlp_install_dialog import YtdlpInstallDialog

        dlg = YtdlpInstallDialog(mode="install")
        dlg.finished_install.connect(results.append)
        dlg.show()  # NOT exec() in tests — showEvent should auto-start.
        # Pump the event loop until the worker reports done so the
        # QThread is cleanly stopped before the dialog is GC'd.
        _pump_until(app, lambda: bool(results), timeout=3.0)
        dlg.close()

    assert started["called"] is True
    assert results == [True]
