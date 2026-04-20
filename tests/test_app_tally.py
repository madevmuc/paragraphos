"""Regression: spot-check notification must respect notify_mode='off'."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import MagicMock


def test_notify_off_fires_zero_tray_messages(monkeypatch, tmp_path):
    import sys

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841

    monkeypatch.setenv("HOME", str(tmp_path))
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    from ui.app_context import AppContext

    ctx = AppContext.load(data_dir)
    ctx.settings.notify_mode = "off"

    from app import ParagraphosApp

    pa = ParagraphosApp.__new__(ParagraphosApp)  # bypass __init__
    pa.ctx = ctx
    pa._run_tally = {}
    pa.tray = MagicMock()
    pa._icon_renderer = MagicMock()

    for i in range(3):
        pa._on_episode_done(
            slug="demo",
            guid=f"g{i}",
            action="transcribed",
            done_idx=i + 1,
            total=3,
            show_title="Demo Show",
            ep_title=f"Ep {i}",
        )

    assert pa.tray.showMessage.call_count == 0
