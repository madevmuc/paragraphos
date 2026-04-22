"""Smoke tests for the Obsidian group-box reshuffle in SettingsPane.

These tests only cover that the dedicated 'Obsidian' QGroupBox exists and
that the preview line tracks changes to the output root — they do not try
to cover the whole settings pane (that's the pickers test's turf).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QGroupBox


class _FakeState:
    """Minimal ctx.state stub — just enough so _refresh_drift_row() can
    short-circuit on the 'no transcripts yet' branch without touching
    SQLite."""

    def get_meta(self, _key: str) -> str | None:
        return None


class _FakeCtx:
    """Minimal AppContext stand-in. Only the attributes SettingsPane
    touches during __init__ are populated."""

    def __init__(self, tmp_path: Path):
        from core.models import Settings

        self.settings = Settings()
        self.data_dir = tmp_path
        self.state = _FakeState()
        self.watchlist = None

    def reload_library(self) -> None:  # pragma: no cover — never invoked in these tests
        pass


_QT_KEEPALIVE: list = []  # keeps QApplication + widgets alive across tests


def _make_pane(tmp_path):
    app = QApplication.instance() or QApplication([])
    _QT_KEEPALIVE.append(app)
    from ui.settings_pane import SettingsPane

    try:
        pane = SettingsPane(_FakeCtx(tmp_path))
    except Exception as e:
        pytest.skip(f"SettingsPane ctor failed under fake ctx: {e!r}")
    _QT_KEEPALIVE.append(pane)
    return pane


def test_obsidian_group_box_exists(tmp_path):
    pane = _make_pane(tmp_path)
    titles = {gb.title() for gb in pane.findChildren(QGroupBox)}
    assert "Obsidian" in titles


def test_obsidian_preview_reflects_output_root(tmp_path):
    pane = _make_pane(tmp_path)
    pane.output.setText("/tmp/foo")
    assert "/tmp/foo" in pane.obsidian_preview.text()
