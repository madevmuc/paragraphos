import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.models import Settings
from ui.setup_dialog import SetupDialog, show_setup_if_needed

_app_ref = QApplication.instance() or QApplication([])
_keepalive: list = []


def _make(settings):
    dlg = SetupDialog(settings)
    _keepalive.append(dlg)
    return dlg


def test_show_setup_returns_immediately_when_completed():
    s = Settings()
    s.setup_completed = True
    assert show_setup_if_needed(s) is True


def test_finish_no_obsidian_writes_output_root(tmp_path):
    s = Settings()
    s.setup_completed = False
    dlg = _make(s)
    dlg._output_edit.setText(str(tmp_path))
    dlg._no_obsidian_btn.setChecked(True)
    dlg._finish()
    assert s.setup_completed is True
    assert s.output_root == str(tmp_path)
    assert s.obsidian_vault_path == ""


def test_finish_obsidian_sets_vault_and_name(tmp_path):
    s = Settings()
    vault = tmp_path / "MyVault"
    (vault / ".obsidian").mkdir(parents=True)
    dlg = _make(s)
    dlg._yes_obsidian_btn.setChecked(True)
    dlg._vault_edit.setText(str(vault))
    dlg._vault_colocate.setChecked(True)
    dlg._finish()
    assert s.setup_completed is True
    assert s.obsidian_vault_path == str(vault)
    assert s.obsidian_vault_name == "MyVault"
    assert s.output_root == str(vault / "raw" / "transcripts")


def test_finish_obsidian_without_colocate_keeps_explicit_output(tmp_path):
    s = Settings()
    vault = tmp_path / "OtherVault"
    (vault / ".obsidian").mkdir(parents=True)
    dlg = _make(s)
    dlg._output_edit.setText(str(tmp_path / "Plain"))
    dlg._yes_obsidian_btn.setChecked(True)
    dlg._vault_edit.setText(str(vault))
    dlg._vault_colocate.setChecked(False)
    dlg._finish()
    assert s.output_root == str(tmp_path / "Plain")
    assert s.obsidian_vault_path == str(vault)
