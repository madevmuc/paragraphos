"""Unit tests for `core.macopen` — subprocess shell-out helpers.

We mock `subprocess.run` to assert the exact argv we'd hand to macOS.
No real `open` / `osascript` calls happen during tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from core import macopen


def test_open_default_invokes_open(tmp_path: Path):
    target = tmp_path / "transcript.md"
    target.write_text("hi", encoding="utf-8")
    with patch("core.macopen.subprocess.run") as run:
        macopen.open_default(target)
    run.assert_called_once()
    args, kwargs = run.call_args
    argv = args[0]
    assert argv[0] == "open"
    assert argv[1] == str(target)
    assert kwargs.get("check") is False


def test_reveal_in_finder_uses_dash_R(tmp_path: Path):
    target = tmp_path / "transcript.md"
    target.write_text("hi", encoding="utf-8")
    with patch("core.macopen.subprocess.run") as run:
        macopen.reveal_in_finder(target)
    argv = run.call_args.args[0]
    assert argv[0] == "open"
    assert "-R" in argv
    assert str(target) in argv


def test_open_with_chooser_invokes_osascript(tmp_path: Path):
    target = tmp_path / "transcript.md"
    target.write_text("hi", encoding="utf-8")
    with patch("core.macopen.subprocess.run") as run:
        macopen.open_with_chooser(target)
    argv = run.call_args.args[0]
    assert argv[0] == "osascript"
    # AppleScript body is passed via -e; assert the chooser invocation
    # is in there somewhere.
    joined = " ".join(argv)
    assert "choose application" in joined
    assert str(target) in joined
