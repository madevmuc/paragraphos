import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication

from ui.install_runner import BrewRunner


def test_brew_runner_streams_lines_and_exits(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])

    # Fake "brew" script prints three lines then exits 0.
    fake = tmp_path / "fake-brew.sh"
    fake.write_text("#!/bin/sh\necho line1\necho line2\necho line3\nexit 0\n")
    fake.chmod(0o755)

    lines = []
    done = {}
    r = BrewRunner([str(fake)])
    r.line.connect(lines.append)
    r.finished.connect(lambda code: done.setdefault("code", code))
    r.start()

    deadline = time.time() + 5
    while "code" not in done and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)

    assert done.get("code") == 0
    assert lines == ["line1", "line2", "line3"]


def test_brew_runner_rejects_double_start(tmp_path):
    _ = QCoreApplication.instance() or QCoreApplication([])
    fake = tmp_path / "fake.sh"
    fake.write_text("#!/bin/sh\nsleep 0.2\n")
    fake.chmod(0o755)
    r = BrewRunner([str(fake)])
    r.start()
    import pytest

    with pytest.raises(RuntimeError):
        r.start()
