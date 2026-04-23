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


def test_setup_dialog_prefills_obsidian_when_vault_detected(tmp_path, monkeypatch):
    """If best_guess_vault returns a path, the Obsidian page defaults to
    YES + pre-populates the path field."""
    fake_vault = tmp_path / "MyVault"
    fake_vault.mkdir()
    (fake_vault / ".obsidian").mkdir()
    monkeypatch.setattr("core.obsidian.best_guess_vault", lambda: fake_vault)
    s = Settings()
    s.setup_completed = False
    dlg = _make(s)
    assert dlg._yes_obsidian_btn.isChecked() is True
    assert dlg._no_obsidian_btn.isChecked() is False
    assert dlg._vault_edit.text() == str(fake_vault)


def test_setup_dialog_defaults_no_when_no_vault(monkeypatch):
    monkeypatch.setattr("core.obsidian.best_guess_vault", lambda: None)
    s = Settings()
    s.setup_completed = False
    dlg = _make(s)
    assert dlg._no_obsidian_btn.isChecked() is True
    assert dlg._yes_obsidian_btn.isChecked() is False
    assert dlg._vault_edit.text() == ""


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
