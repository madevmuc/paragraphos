from pathlib import Path
from unittest.mock import MagicMock, patch

from core.youtube_captions import (
    NoCaptionsAvailable,
    fetch_manual_captions,
    vtt_to_srt,
)

FIXTURE = Path(__file__).parent / "fixtures" / "youtube" / "sample.en.vtt"


def _setup_fake_ytdlp(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)


def test_vtt_to_srt_converts_basic_cue():
    vtt = FIXTURE.read_text()
    srt = vtt_to_srt(vtt)
    assert "1\n" in srt
    assert " --> " in srt
    assert ",000" in srt or "," in srt  # SRT uses commas in timestamps


def test_fetch_manual_returns_path(tmp_path, monkeypatch):
    _setup_fake_ytdlp(tmp_path, monkeypatch)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    written_vtt = out_dir / "video.en.vtt"
    written_vtt.write_text(FIXTURE.read_text())

    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        srt_path = fetch_manual_captions("dQw4w9WgXcQ", out_dir / "video", lang="en")
        assert srt_path.exists()
        assert srt_path.suffix == ".srt"


def test_fetch_manual_raises_when_no_captions(tmp_path, monkeypatch):
    _setup_fake_ytdlp(tmp_path, monkeypatch)
    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        try:
            fetch_manual_captions("vid", tmp_path / "video", lang="en")
        except NoCaptionsAvailable:
            return
        raise AssertionError("expected NoCaptionsAvailable")
