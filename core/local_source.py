"""Universal-ingest helpers: local files, folders, and arbitrary URLs.

Three entry points (drop zone, watch folder, folder import) funnel into
the existing ``shows → episodes`` model via synthetic shows. See
``docs/plans/2026-04-23-universal-ingest-design.md``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
from pathlib import Path

from core.sanitize import slugify
from core.state import StateStore

logger = logging.getLogger(__name__)

# Extracted to a module attribute so tests can monkey-patch it and prove
# the mtime+size cache really short-circuits rehashing.
_hashlib_sha256 = hashlib.sha256

# Bytes per read chunk when hashing large files. 1 MiB matches macOS
# APFS's block-read sweet-spot and keeps peak RSS flat.
_HASH_CHUNK = 1024 * 1024


def sha256_of(path: Path, *, state: StateStore) -> str:
    """Return the hex SHA-256 of ``path``, using a (abs_path, size, mtime)
    cache stored in ``state.meta["filehash:<abs_path>"]``.

    Cache format: ``"<size>:<mtime_ns>:<hex>"``. Anything else (missing,
    malformed, size/mtime mismatch) triggers a real hash.
    """
    p = Path(path).resolve()
    st = p.stat()
    meta_key = f"filehash:{p}"

    cached = state.get_meta(meta_key)
    if cached:
        try:
            size_s, mtime_s, hex_s = cached.split(":", 2)
            if int(size_s) == st.st_size and int(mtime_s) == st.st_mtime_ns:
                return hex_s
        except (ValueError, IndexError):
            pass  # malformed — rehash

    h = _hashlib_sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    hex_s = h.hexdigest()
    state.set_meta(meta_key, f"{st.st_size}:{st.st_mtime_ns}:{hex_s}")
    return hex_s


def slug_for_drop() -> str:
    """Default show slug for drag-drop files with no user-picked show."""
    return "files"


def slug_for_watch(file_path: Path, root: Path) -> str:
    """Top-level subfolder under ``root`` → show slug. Loose files at the
    root go to the default drop slug ``files`` so they don't silently
    create a show named after the root directory itself."""
    try:
        rel = Path(file_path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return slug_for_drop()
    parts = rel.parts
    if len(parts) < 2:
        return slug_for_drop()
    return slugify(parts[0])


def slug_for_folder_import(folder: Path, *, override: str | None) -> str:
    """Slug for a one-shot folder import: ``override`` wins, else folder
    basename slugified."""
    if override:
        return slugify(override)
    return slugify(Path(folder).name)


def slug_for_url(url: str, *, uploader: str | None) -> str:
    """Slug for a pasted URL: uploader → slug; otherwise ``web`` catch-all."""
    if uploader:
        return slugify(uploader)
    return "web"


def _ffprobe_bin() -> str:
    """Find ``ffprobe``. Mirrors core.transcriber._locate_ffmpeg_dir so a
    .app launch with a bare PATH still finds Homebrew ffprobe."""
    found = shutil.which("ffprobe")
    if found:
        return found
    for p in ("/opt/homebrew/bin/ffprobe", "/usr/local/bin/ffprobe"):
        if Path(p).exists():
            return p
    return "/opt/homebrew/bin/ffprobe"  # surface via existence check at call time


def has_audio_stream(path: Path) -> bool:
    """True if ffprobe reports at least one ``audio`` stream on ``path``.
    Returns False on any ffprobe error (missing binary, corrupt file,
    unreadable path) — caller turns that into a user-visible Failed
    reason without crashing."""
    try:
        r = subprocess.run(
            [
                _ffprobe_bin(),
                "-v",
                "error",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0 or not r.stdout:
        return False
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return False
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            return True
    return False


def duration_seconds(path: Path) -> int | None:
    """Return the media's duration in whole seconds, or None if ffprobe
    can't tell. Used for the over-cap guard and for populating
    ``episodes.duration_sec``."""
    try:
        r = subprocess.run(
            [
                _ffprobe_bin(),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    try:
        data = json.loads(r.stdout)
        dur = float(data.get("format", {}).get("duration", 0))
        return int(dur) if dur > 0 else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
