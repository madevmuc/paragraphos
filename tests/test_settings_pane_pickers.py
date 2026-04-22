import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication


def _bare_pane():
    """Fallback construction path — avoids any fixture dependencies the
    real __init__ may pull in. Only the fields the helper touches are set."""
    _ = QApplication.instance() or QApplication([])
    from ui.settings_pane import SettingsPane

    pane = SettingsPane.__new__(SettingsPane)
    return pane


def test_default_picker_dir_falls_back_to_desktop_on_empty():
    pane = _bare_pane()
    assert pane._default_picker_dir("") == str(Path.home() / "Desktop")


def test_default_picker_dir_falls_back_to_desktop_on_missing():
    pane = _bare_pane()
    assert pane._default_picker_dir("/nonexistent/path/here") == str(Path.home() / "Desktop")


def test_default_picker_dir_preserves_existing_path(tmp_path):
    pane = _bare_pane()
    assert pane._default_picker_dir(str(tmp_path)) == str(tmp_path)


def test_pickers_source_code_references_helper():
    """Guard that all four pickers are wired through _default_picker_dir —
    full SettingsPane construction needs an AppContext with state/etc.,
    and a QWidget instantiated via __new__ without __init__ segfaults
    when any Qt method touches self (including QFileDialog parenting).
    A source-level assertion is the pragmatic way to pin the rewire."""
    from pathlib import Path as _P

    src = _P(__file__).resolve().parents[1] / "ui" / "settings_pane.py"
    text = src.read_text()
    for method in ("_pick_dir", "_pick_kb_root", "_pick_obsidian", "_pick_export"):
        # find the def, assert the next "start = " line uses the helper
        idx = text.index(f"def {method}(")
        snippet = text[idx : idx + 400]
        assert "self._default_picker_dir(" in snippet, f"{method} does not use _default_picker_dir"
