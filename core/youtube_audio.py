"""Audio-only YouTube download via yt-dlp, mapping to the existing
podcast-MP3 pipeline so transcribe.py treats it identically."""

from __future__ import annotations

import subprocess
from pathlib import Path

from core import ytdlp


class YoutubeDownloadError(RuntimeError):
    pass


def download_audio(video_id: str, target_mp3: Path, *, timeout: int = 600) -> Path:
    if not ytdlp.is_installed():
        raise YoutubeDownloadError("yt-dlp not installed")
    target_mp3.parent.mkdir(parents=True, exist_ok=True)
    template = str(target_mp3.with_suffix(""))
    cmd = [
        str(ytdlp.ytdlp_path()),
        "-f",
        "bestaudio",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        f"{template}.%(ext)s",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise YoutubeDownloadError(proc.stderr.strip() or "unknown")
    if not target_mp3.exists():
        raise YoutubeDownloadError(f"yt-dlp did not produce {target_mp3}")
    return target_mp3
