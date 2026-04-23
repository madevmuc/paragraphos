"""yt-dlp lazy-installer + self-update wrapper.

yt-dlp lives at ~/Library/Application Support/Paragraphos/bin/yt-dlp,
NOT inside the .app bundle, so `yt-dlp -U` can replace itself without
breaking the app signature.

Public API:
- ytdlp_path() -> Path
- is_installed() -> bool
- install(progress=cb) -> None         (downloads from GitHub releases)
- self_update() -> None                (runs `yt-dlp -U`)
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from typing import Callable, Optional

from core.http import get_client
from core.paths import user_data_dir

APP_SUPPORT: Path = user_data_dir()
DOWNLOAD_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"


class YtdlpError(RuntimeError):
    """yt-dlp install or update failed."""


def ytdlp_path() -> Path:
    return APP_SUPPORT / "bin" / "yt-dlp"


def is_installed() -> bool:
    p = ytdlp_path()
    return p.exists() and bool(p.stat().st_mode & stat.S_IXUSR)


def install(progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Download yt-dlp to the user-writable bin dir.

    `progress(done_bytes, total_bytes)` is called periodically so the
    UI can show a progress bar.
    """
    target = ytdlp_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    client = get_client()
    try:
        with client.stream("GET", DOWNLOAD_URL, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        tmp.replace(target)
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        raise YtdlpError(f"yt-dlp download failed: {e}") from e


def self_update() -> None:
    """Run `yt-dlp -U` in place. Raises YtdlpError on non-zero exit."""
    if not is_installed():
        raise YtdlpError("yt-dlp not installed; call install() first")
    p = ytdlp_path()
    proc = subprocess.run([str(p), "-U"], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise YtdlpError(f"yt-dlp -U failed: {proc.stderr.strip()}")
