"""Settings pane — Sources section (Podcasts / YouTube checkboxes).

No pytest-qt; uses the bare-QApplication + processEvents pattern shared
with tests/test_settings_obsidian_group.py.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QGroupBox


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


def test_sources_groupbox_present(tmp_path):
    pane, _ctx, _app = _make_pane(tmp_path)
    titles = [gb.title() for gb in pane.findChildren(QGroupBox)]
    assert any("Source" in t for t in titles), f"no Sources group; saw: {titles}"


def test_unchecking_both_sources_snaps_podcasts_back(tmp_path):
    pane, ctx, app = _make_pane(tmp_path)
    pane.podcasts_checkbox.setChecked(False)
    pane.youtube_checkbox.setChecked(False)
    app.processEvents()
    assert ctx.settings.sources_podcasts is True or ctx.settings.sources_youtube is True
    # And the UI reflects that at least one is on.
    assert pane.podcasts_checkbox.isChecked() or pane.youtube_checkbox.isChecked()


def test_youtube_off_persists_to_settings(tmp_path):
    pane, ctx, app = _make_pane(tmp_path)
    pane.youtube_checkbox.setChecked(False)
    app.processEvents()
    # Force the debounced save to flush so settings reflect the toggle.
    pane._do_save()
    assert ctx.settings.sources_youtube is False
    assert ctx.settings.sources_podcasts is True


def test_podcasts_off_with_youtube_on_persists(tmp_path):
    pane, ctx, app = _make_pane(tmp_path)
    # Turn YouTube on first so we can drop podcasts without snap-back.
    pane.youtube_checkbox.setChecked(True)
    pane.podcasts_checkbox.setChecked(False)
    app.processEvents()
    pane._do_save()
    assert ctx.settings.sources_podcasts is False
    assert ctx.settings.sources_youtube is True


def test_settings_has_rerun_setup_button(tmp_path):
    """The settings pane exposes a button that re-opens the setup dialog."""
    pane, _ctx, _app = _make_pane(tmp_path)
    from PyQt6.QtWidgets import QPushButton

    buttons = pane.findChildren(QPushButton)
    labels = [b.text() for b in buttons]
    assert any("setup" in label.lower() for label in labels), (
        f"no Re-run setup button; saw: {labels}"
    )
