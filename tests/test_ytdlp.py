from pathlib import Path
from unittest.mock import MagicMock, patch

from core.ytdlp import (
    YtdlpError,
    install,
    is_installed,
    self_update,
    ytdlp_path,
)


def test_ytdlp_path_is_under_app_support(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    p = ytdlp_path()
    assert p == tmp_path / "bin" / "yt-dlp"


def test_is_installed_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    assert not is_installed()


def test_is_installed_true_when_executable(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    p = tmp_path / "bin" / "yt-dlp"
    p.parent.mkdir(parents=True)
    p.write_text("#!/bin/sh\necho yt-dlp 2026.03.30\n")
    p.chmod(0o755)
    assert is_installed()


def test_install_downloads_and_chmods(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    fake_http = MagicMock()
    fake_http.stream.return_value.__enter__.return_value.iter_bytes.return_value = [b"#!/bin/sh\n"]
    fake_http.stream.return_value.__enter__.return_value.headers = {"content-length": "10"}
    with patch("core.ytdlp.get_client", return_value=fake_http):
        install(progress=lambda done, total: None)
    p = tmp_path / "bin" / "yt-dlp"
    assert p.exists()
    assert p.stat().st_mode & 0o111  # executable bit set


def test_self_update_invokes_yt_dlp_dash_U(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    p = tmp_path / "bin" / "yt-dlp"
    p.parent.mkdir(parents=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o755)
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        self_update()
        run.assert_called_once()
        assert run.call_args[0][0] == [str(p), "-U"]
