import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.first_run_wizard import StepRow


def test_step_row_waiting_state_hides_action_btn():
    _ = QApplication.instance() or QApplication([])
    row = StepRow("whisper-cpp")
    row.set_waiting("waiting for Homebrew")
    assert not row.action_btn.isVisible()
    assert "waiting" in row.subcopy.text().lower()


def test_step_row_set_sub_line_updates_subcopy():
    _ = QApplication.instance() or QApplication([])
    row = StepRow("whisper-cpp")
    row.set_running("installing… 3s")
    row.set_sub_line("Pouring whisper-cpp-1.7.5.arm64.bottle.tar.gz")
    assert "Pouring" in row.subcopy.text()


def test_step_row_set_sub_line_truncates_long_input():
    _ = QApplication.instance() or QApplication([])
    row = StepRow("whisper-cpp")
    long = "x" * 200
    row.set_sub_line(long)
    assert len(row.subcopy.text()) <= 80
    assert row.subcopy.text().endswith("…")


def test_wizard_auto_starts_model_download_when_missing(monkeypatch):
    _ = QApplication.instance() or QApplication([])

    from core import deps
    from ui import first_run_wizard as wiz

    # brew present, whisper+ffmpeg+model missing.
    monkeypatch.setattr(
        deps,
        "check",
        lambda: deps.DepStatus(brew=True, whisper_cli=False, ffmpeg=False, model=False),
    )

    started = {"model": False, "whisper": False}
    monkeypatch.setattr(
        wiz.FirstRunWizard, "_download_model", lambda self: started.__setitem__("model", True)
    )
    monkeypatch.setattr(
        wiz.FirstRunWizard, "_install_whisper", lambda self: started.__setitem__("whisper", True)
    )
    monkeypatch.setattr(wiz.FirstRunWizard, "_install_ffmpeg", lambda self: None)

    w = wiz.FirstRunWizard()
    w._refresh()  # single entry point; no processEvents hack needed.

    assert started["model"] is True
    assert started["whisper"] is True  # auto-chained because brew is present


def test_wizard_fires_whisper_only_once(monkeypatch):
    _ = QApplication.instance() or QApplication([])

    from core import deps
    from ui import first_run_wizard as wiz

    monkeypatch.setattr(
        deps,
        "check",
        lambda: deps.DepStatus(brew=True, whisper_cli=False, ffmpeg=False, model=True),
    )

    calls = {"whisper": 0}
    monkeypatch.setattr(
        wiz.FirstRunWizard,
        "_install_whisper",
        lambda self: calls.__setitem__("whisper", calls["whisper"] + 1),
    )
    monkeypatch.setattr(wiz.FirstRunWizard, "_install_ffmpeg", lambda self: None)
    monkeypatch.setattr(wiz.FirstRunWizard, "_download_model", lambda self: None)

    w = wiz.FirstRunWizard()
    w._refresh()
    w._refresh()
    w._refresh()

    assert calls["whisper"] == 1


def test_wizard_ffmpeg_waits_for_whisper(monkeypatch):
    _ = QApplication.instance() or QApplication([])

    from core import deps
    from ui import first_run_wizard as wiz

    # brew ok, whisper STILL missing, ffmpeg missing.
    monkeypatch.setattr(
        deps,
        "check",
        lambda: deps.DepStatus(brew=True, whisper_cli=False, ffmpeg=False, model=True),
    )
    monkeypatch.setattr(wiz.FirstRunWizard, "_install_whisper", lambda self: None)
    monkeypatch.setattr(wiz.FirstRunWizard, "_install_ffmpeg", lambda self: None)
    monkeypatch.setattr(wiz.FirstRunWizard, "_download_model", lambda self: None)

    w = wiz.FirstRunWizard()
    w._refresh()

    assert "waiting for whisper-cpp" in w.ffmpeg_row.subcopy.text().lower()


def test_whisper_install_failure_re_attaches_retry(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    from ui import first_run_wizard as wiz

    w = wiz.FirstRunWizard()
    w.show()  # parent must be visible for child action_btn.isVisible() to be True.
    # Simulate a previous failed install.
    w._whisper_started = True
    w._after_cli(w.whisper_row, ok=False, err="brew: download failed")
    # Flag reset, row's action button visible and labelled Retry.
    assert w._whisper_started is False
    assert w.whisper_row.action_btn.isVisible()
    assert w.whisper_row.action_btn.text() == "Retry"
