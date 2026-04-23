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


def test_run_brew_pins_runner_and_shows_elapsed(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    from PyQt6.QtCore import QObject, pyqtSignal

    from ui import first_run_wizard as wiz
    from ui import install_runner

    started = {"cmd": None, "start_called": False}

    class StubRunner(QObject):
        line = pyqtSignal(str)
        finished = pyqtSignal(int)

        def __init__(self, cmd, parent=None):
            super().__init__(parent)
            started["cmd"] = cmd

        def start(self):
            started["start_called"] = True

    monkeypatch.setattr(install_runner, "BrewRunner", StubRunner)
    # Neutralise the deps-check inside _refresh so the on_finished closure's
    # trailing _refresh() call doesn't re-trigger the auto-chain (brew=True
    # + whisper missing + _whisper_started=False would re-fire _install_whisper
    # and flip the pill back to "installing…"). CI runners have brew on PATH
    # but no whisper-cli; the author's Mac has both, which is why this only
    # trips in CI.
    from core import deps

    monkeypatch.setattr(
        deps,
        "check",
        lambda: deps.DepStatus(brew=False, whisper_cli=False, ffmpeg=False, model=True),
    )

    w = wiz.FirstRunWizard()
    w._run_brew(w.whisper_row, ["brew", "install", "whisper-cpp"], label="whisper-cpp")

    assert started["cmd"] == ["brew", "install", "whisper-cpp"]
    assert started["start_called"] is True
    assert "whisper-cpp" in w._runners
    assert isinstance(w._runners["whisper-cpp"], StubRunner)
    assert "installing" in w.whisper_row.pill.text()

    # Simulate the brew process completing successfully — the row should
    # transition off the "installing…" pill via _after_cli.
    from PyQt6.QtCore import QCoreApplication

    runner = w._runners["whisper-cpp"]
    runner.finished.emit(0)
    QCoreApplication.processEvents()
    assert "installing" not in w.whisper_row.pill.text().lower()


def test_wizard_blocks_continue_on_intel(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    from core import compat, deps
    from ui import first_run_wizard as wiz

    monkeypatch.setattr(
        compat,
        "check_compat",
        lambda: compat.CompatStatus(
            blocking_reasons=["Apple Silicon required — this Mac reports arch 'x86_64'."]
        ),
    )
    # Deps all missing — makes the "no install kicked off" assertion meaningful.
    monkeypatch.setattr(
        deps,
        "check",
        lambda: deps.DepStatus(brew=False, whisper_cli=False, ffmpeg=False, model=False),
    )
    started = {"brew": False, "whisper": False, "ffmpeg": False, "model": False}
    monkeypatch.setattr(
        wiz.FirstRunWizard, "_install_brew", lambda self: started.__setitem__("brew", True)
    )
    monkeypatch.setattr(
        wiz.FirstRunWizard, "_install_whisper", lambda self: started.__setitem__("whisper", True)
    )
    monkeypatch.setattr(
        wiz.FirstRunWizard, "_install_ffmpeg", lambda self: started.__setitem__("ffmpeg", True)
    )
    monkeypatch.setattr(
        wiz.FirstRunWizard, "_download_model", lambda self: started.__setitem__("model", True)
    )

    w = wiz.FirstRunWizard()
    w._refresh()

    assert not w.close_btn.isEnabled()
    assert "Apple Silicon" in w.compat_row.subcopy.text()
    # Nothing kicks off when hardware is unsupported.
    assert not any(started.values())
    # All dep rows parked in waiting state.
    assert "unsupported" in w.brew_row.subcopy.text().lower()


def test_wizard_advisory_shows_but_allows_continue(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    from core import compat, deps
    from ui import first_run_wizard as wiz

    # Compat: advisory-only, all deps present.
    monkeypatch.setattr(
        compat,
        "check_compat",
        lambda: compat.CompatStatus(
            advisories=["Only 6 GB RAM detected — transcription will be slow (≥ 8 GB recommended)."]
        ),
    )
    monkeypatch.setattr(
        deps,
        "check",
        lambda: deps.DepStatus(brew=True, whisper_cli=True, ffmpeg=True, model=True),
    )
    monkeypatch.setattr(wiz.FirstRunWizard, "_install_whisper", lambda self: None)
    monkeypatch.setattr(wiz.FirstRunWizard, "_install_ffmpeg", lambda self: None)
    monkeypatch.setattr(wiz.FirstRunWizard, "_download_model", lambda self: None)

    w = wiz.FirstRunWizard()
    w._refresh()

    assert w.close_btn.isEnabled()
    assert "RAM" in w.compat_row.subcopy.text()
    assert "advisor" in w.compat_row.pill.text().lower()
