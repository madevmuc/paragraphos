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
