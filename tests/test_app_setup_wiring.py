"""Static guards that the setup-dialog wiring is hooked into app.py
and the Help menu.

Functional behaviour of ``SetupDialog`` / ``show_setup_if_needed`` is
covered by ``tests/test_setup_dialog.py``; these tests just ensure the
wiring-up call sites exist. Launching app.py directly would spin the
Qt event loop and the tray icon, so we inspect source instead.
"""

from __future__ import annotations

import inspect

import app


def test_app_references_setup_dialog() -> None:
    """app.py must import show_setup_if_needed and backfill_setup_completed."""
    src = inspect.getsource(app)
    assert "show_setup_if_needed" in src
    assert "backfill_setup_completed" in src


def test_menu_bar_has_rerun_setup() -> None:
    import ui.menu_bar as mb

    src = inspect.getsource(mb)
    assert "Re-run setup guide" in src
    assert "SetupDialog" in src
