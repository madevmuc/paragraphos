"""yt-dlp metadata wrappers for channel preview + video enumeration."""

from __future__ import annotations

import json
import subprocess
from typing import Dict, List

from core import ytdlp


class YoutubeMetaError(RuntimeError):
    """yt-dlp returned an error or unparseable output."""


def _run_ytdlp(args: List[str], timeout: int = 60) -> str:
    if not ytdlp.is_installed():
        raise YoutubeMetaError("yt-dlp not installed")
    cmd = [str(ytdlp.ytdlp_path()), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise YoutubeMetaError(f"yt-dlp failed: {proc.stderr.strip() or 'unknown error'}")
    return proc.stdout


def resolve_handle_to_channel_id(handle: str) -> str:
    out = _run_ytdlp(
        [
            "--skip-download",
            "--print",
            "%(channel_id)j",
            f"https://www.youtube.com/@{handle}",
        ]
    )
    line = out.strip().splitlines()[0]
    parsed = json.loads(line) if line.startswith('"') else json.loads(out.strip())
    if isinstance(parsed, dict):
        return parsed.get("channel_id") or ""
    return parsed


def fetch_channel_preview(channel_id: str) -> Dict[str, object]:
    """Return {title, video_count, artwork_url, channel_id}."""
    out = _run_ytdlp(
        [
            "--skip-download",
            "--playlist-items",
            "0",
            "--dump-single-json",
            f"https://www.youtube.com/channel/{channel_id}",
        ]
    )
    data = json.loads(out)
    thumbs = data.get("thumbnails") or []
    artwork = thumbs[-1]["url"] if thumbs else ""
    return {
        "channel_id": data.get("channel_id") or channel_id,
        "title": data.get("channel") or data.get("title") or "",
        "video_count": int(data.get("playlist_count") or 0),
        "artwork_url": artwork,
    }


def enumerate_channel_videos(channel_id: str, *, limit: int | None = None) -> List[Dict]:
    args = [
        "--flat-playlist",
        "--dump-json",
        f"https://www.youtube.com/channel/{channel_id}",
    ]
    if limit:
        args[1:1] = ["--playlist-end", str(limit)]
    out = _run_ytdlp(args, timeout=180)
    return [json.loads(line) for line in out.splitlines() if line.strip()]
