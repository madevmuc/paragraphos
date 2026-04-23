"""Whisper-cli subprocess gets ffmpeg on its PATH.

A user crash bucket landed because Paragraphos.app launched from
/Applications has PATH=/usr/bin:/bin only — Homebrew binaries are
invisible. Whisper-cli shells out to ffmpeg internally for non-WAV
inputs (m4a, mp4 podcasts), so without ffmpeg it exited 0 with no
transcript output ~700 ms later for any non-WAV file. The 4 stuck
``hausverwalter-inside`` failures with .mp4/.m4a URLs are the
fingerprint.

These tests pin the locator + env-augmenter so that regression
doesn't return.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from core import transcriber


def test_locate_ffmpeg_dir_returns_none_when_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert transcriber._locate_ffmpeg_dir() is None


def test_locate_ffmpeg_dir_prefers_PATH(monkeypatch):
    monkeypatch.setattr(
        "shutil.which", lambda name: "/some/where/ffmpeg" if name == "ffmpeg" else None
    )
    assert transcriber._locate_ffmpeg_dir() == "/some/where"


def test_locate_ffmpeg_dir_falls_back_to_homebrew(monkeypatch):
    """When PATH is restricted (.app launched from /Applications), the
    locator must still find Homebrew's ffmpeg via the hardcoded fallback
    list. Without this, whisper-cli silently fails on m4a/mp4 inputs."""
    monkeypatch.setattr("shutil.which", lambda _: None)

    def fake_exists(self):
        return str(self) == "/opt/homebrew/bin/ffmpeg"

    monkeypatch.setattr(Path, "exists", fake_exists)
    assert transcriber._locate_ffmpeg_dir() == "/opt/homebrew/bin"


def test_subprocess_env_returns_none_when_no_ffmpeg(monkeypatch):
    """No augmentation = inherit os.environ. Keeps existing tests that
    mock subprocess.run untouched."""
    monkeypatch.setattr(transcriber, "_FFMPEG_DIR", None)
    assert transcriber._whisper_subprocess_env() is None


def test_subprocess_env_returns_none_when_already_on_path(monkeypatch):
    """Don't bother building a new env dict if PATH already has it —
    subprocess defaults to inheritance, which is cheaper."""
    monkeypatch.setattr(transcriber, "_FFMPEG_DIR", "/opt/homebrew/bin")
    monkeypatch.setenv("PATH", "/usr/bin:/opt/homebrew/bin:/bin")
    assert transcriber._whisper_subprocess_env() is None


def test_subprocess_env_prepends_ffmpeg_dir_when_missing(monkeypatch):
    """The fix: when ffmpeg is locatable but absent from PATH, return
    an env dict with the ffmpeg directory prepended. Whisper-cli's
    internal call to ffmpeg then resolves."""
    monkeypatch.setattr(transcriber, "_FFMPEG_DIR", "/opt/homebrew/bin")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = transcriber._whisper_subprocess_env()
    assert env is not None
    assert env["PATH"].startswith("/opt/homebrew/bin:")
    # Other env vars must be preserved (HOME, LANG, etc. — whisper.cpp
    # reads HOME for its model cache directory).
    assert "HOME" in env or os.environ.get("HOME") is None


def test_subprocess_env_handles_empty_path(monkeypatch):
    """Pathological env where PATH is unset at all — return just the
    ffmpeg dir, don't crash trying to split a None."""
    monkeypatch.setattr(transcriber, "_FFMPEG_DIR", "/opt/homebrew/bin")
    monkeypatch.delenv("PATH", raising=False)
    env = transcriber._whisper_subprocess_env()
    assert env is not None
    assert env["PATH"] == "/opt/homebrew/bin"


def test_transcribe_passes_env_to_subprocess(monkeypatch, tmp_path):
    """End-to-end: transcribe_episode → subprocess.run gets env=...
    when ffmpeg is locatable but missing from PATH. Captures the
    actual call so the wiring (not just the helper) is pinned."""
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        # Touch the expected outputs so transcribe_episode's
        # missing-output check passes — we're testing the env wiring
        # here, not the post-processing.
        idx = cmd.index("-of")
        stem = Path(cmd[idx + 1])
        # Write enough words to clear the MIN_WPM_GUARD silence-check;
        # we're testing env-passing, not the post-processing.
        stem.with_suffix(".txt").write_text(" ".join(["wort"] * 50))
        stem.with_suffix(".srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n" + " ".join(["wort"] * 50) + "\n"
        )

        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(transcriber, "_FFMPEG_DIR", "/opt/homebrew/bin")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    # Skip the engine-fingerprint probe (tries to spawn whisper).
    monkeypatch.setattr(
        "core.engine_version.current_fingerprint",
        lambda *a, **kw: {},
    )
    # And the model existence check.
    monkeypatch.setattr(Path, "exists", lambda self: True)

    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"\x00" * 1024)
    out = tmp_path / "out"
    out.mkdir()

    transcriber.transcribe_episode(
        mp3_path=mp3,
        output_dir=out,
        slug="ep",
        metadata={"title": "ep", "guid": "g", "pub_date": "2025-01-01"},
        whisper_prompt="",
    )

    assert captured["env"] is not None, "subprocess.run was called with env=None"
    assert captured["env"]["PATH"].startswith("/opt/homebrew/bin:")
