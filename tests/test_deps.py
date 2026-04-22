"""Tests for core.deps — dependency detection + brew-install invocations."""

from __future__ import annotations

from unittest.mock import patch

from core import deps


def test_whisper_cli_detected_via_usr_local(tmp_path, monkeypatch):
    fake = tmp_path / "whisper-cli"
    fake.write_text("")
    fake.chmod(0o755)

    monkeypatch.setenv("PATH", str(tmp_path))
    # Point _EXTRA_PATH at the throwaway dir so _has_any's shutil.which
    # resolves the fake binary without clobbering the real system PATH.
    with patch.object(deps, "_EXTRA_PATH", str(tmp_path)):
        status = deps.check()
    assert status.whisper_cli


def test_brew_env_augments_empty_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = deps._brew_env()
    assert "/opt/homebrew/bin" in env["PATH"]
    # Respect existing PATH: user's entries stay in place.
    assert env["PATH"].startswith("/usr/bin:/bin")


def test_install_whisper_cpp_uses_brew_env(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output=False, text=False, env=None):  # noqa: ARG001
        captured["env"] = env

        class R:
            returncode = 0
            stderr = ""

        return R()

    monkeypatch.setattr(deps.subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    deps.install_whisper_cpp()
    assert captured["env"] is not None
    assert "/opt/homebrew/bin" in captured["env"]["PATH"]
