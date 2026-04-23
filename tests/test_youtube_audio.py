from unittest.mock import MagicMock, patch

from core.youtube_audio import download_audio


def test_download_audio_invokes_correct_ytdlp_args(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    target = tmp_path / "out" / "video.mp3"
    target.parent.mkdir()

    def fake_run(cmd, **kw):
        target.write_bytes(b"fake mp3")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run) as run:
        result = download_audio("dQw4w9WgXcQ", target)
        assert result == target
        cmd = run.call_args[0][0]
        assert "--extract-audio" in cmd
        assert "--audio-format" in cmd
        assert "mp3" in cmd
