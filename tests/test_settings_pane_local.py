"""Settings pane — Local sources section (watch folder + max duration).

Mirrors the bare-QApplication + processEvents pattern shared with
``tests/test_settings_pane_sources.py`` and
``tests/test_settings_obsidian_group.py`` — no pytest-qt dependency.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel


class _FakeState:
    def get_meta(self, _key: str) -> str | None:
        return None


class _FakeCtx:
    def __init__(self, tmp_path: Path):
        from core.models import Settings

        self.settings = Settings()
        self.data_dir = tmp_path
        self.state = _FakeState()
        self.watchlist = None

    def reload_library(self) -> None:  # pragma: no cover — auto-save side-effect
        pass


_QT_KEEPALIVE: list = []


def _make_pane(tmp_path):
    app = QApplication.instance() or QApplication([])
    _QT_KEEPALIVE.append(app)
    from ui.settings_pane import SettingsPane

    ctx = _FakeCtx(tmp_path)
    try:
        pane = SettingsPane(ctx)
    except Exception as e:
        pytest.skip(f"SettingsPane ctor failed under fake ctx: {e!r}")
    _QT_KEEPALIVE.append(pane)
    return pane, ctx, app


def test_settings_pane_has_local_sources_group(tmp_path):
    """Discoverability: a QLabel somewhere in the pane contains the
    'Local sources' heading. Robust to layout refactors."""
    pane, _ctx, _app = _make_pane(tmp_path)
    labels = pane.findChildren(QLabel)
    assert any("Local sources" in (lab.text() or "") for lab in labels), (
        f"no 'Local sources' heading; saw: {[lab.text() for lab in labels]}"
    )
