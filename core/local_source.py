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
from datetime import date, datetime, timezone
from pathlib import Path

from core.models import Show, Watchlist
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


def probe_audio_state(path: Path) -> str:
    """Return one of ``'audio'`` | ``'no_audio'`` | ``'error'``.

    Used by the watch folder to distinguish "file had no audio" (final
    answer, don't retry) from "ffprobe had a problem" (file may still
    be writing — worth one retry).
    """
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
        return "error"
    if r.returncode != 0 or not r.stdout:
        return "error"
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return "error"
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            return "audio"
    return "no_audio"


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


# Extensions ffmpeg handles on the audio-extract path. We gate on this
# set rather than asking ffprobe blindly on every file in a directory
# scan — keeps a folder-import of a mixed directory cheap.
_MEDIA_EXTS = frozenset(
    {
        ".mp3",
        ".m4a",
        ".m4b",
        ".wav",
        ".aiff",
        ".aif",
        ".flac",
        ".ogg",
        ".oga",
        ".opus",
        ".mp4",
        ".m4v",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".wmv",
    }
)


class IngestError(ValueError):
    """Raised when a file/folder/URL cannot be ingested. Message is safe
    to surface to the user as the Failed reason."""


def _ensure_show(
    slug: str,
    *,
    source: str,
    title: str,
    watchlist_path: Path,
) -> None:
    """Create the synthetic show in watchlist.yaml if missing. Idempotent."""
    wl = Watchlist.load(watchlist_path)
    if any(s.slug == slug for s in wl.shows):
        return
    wl.shows.append(
        Show(
            slug=slug,
            title=title,
            rss="",  # synthetic shows have no feed
            source=source,
            enabled=True,
            whisper_prompt="",
            language="",  # inherit default
        )
    )
    wl.save(watchlist_path)


def _format_upload_date(yyyymmdd: str) -> str:
    """yt-dlp returns ``YYYYMMDD``; state expects ``YYYY-MM-DD``."""
    if len(yyyymmdd) == 8 and yyyymmdd.isdigit():
        return f"{yyyymmdd[0:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:8]}"
    return yyyymmdd or date.today().isoformat()


def ingest_file(
    path: Path,
    *,
    show_slug: str | None,
    state: StateStore,
    watchlist_path: Path,
    source: str = "local-drop",
    max_duration_hours: int = 4,
) -> str:
    """Ingest one local file. Returns the episode GUID.

    Raises :class:`IngestError` for unsupported formats, missing audio,
    over-cap duration, or unreadable files. Creates the target show on
    first use.
    """
    p = Path(path).resolve()
    if p.suffix.lower() not in _MEDIA_EXTS:
        raise IngestError(f"unsupported format: {p.suffix or '<no ext>'}")
    if not p.exists():
        raise IngestError(f"file does not exist: {p}")

    if not has_audio_stream(p):
        raise IngestError("file has no audio stream (video-only or unreadable)")

    dur = duration_seconds(p)
    if dur is not None and dur > max_duration_hours * 3600:
        raise IngestError(
            f"exceeds duration cap ({max_duration_hours} h) — change "
            "Settings → Local sources if intentional"
        )

    slug = show_slug or slug_for_drop()
    title_fallback = p.stem[:120]
    _ensure_show(
        slug,
        source=source,
        title=title_fallback if slug == slug_for_drop() else slug,
        watchlist_path=watchlist_path,
    )

    guid = f"sha256:{sha256_of(p, state=state)}"
    # pub_date: file's mtime-date (round to day)
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).date()
    state.upsert_episode(
        show_slug=slug,
        guid=guid,
        title=p.stem,
        pub_date=mtime.isoformat(),
        mp3_url=p.as_uri(),
        duration_sec=dur,
    )
    # Remember the origin path for the pipeline copy-or-symlink step.
    state.set_meta(f"local_path:{guid}", str(p))
    return guid


def ingest_folder(
    folder: Path,
    *,
    show_slug: str | None,
    state: StateStore,
    watchlist_path: Path,
    recursive: bool = True,
    max_duration_hours: int = 4,
) -> list[str]:
    """One-shot folder import: queue every supported media file under
    ``folder``. Non-media files and files already ingested (same sha256)
    are silently skipped.
    """
    folder = Path(folder).resolve()
    slug = slug_for_folder_import(folder, override=show_slug)
    it = folder.rglob("*") if recursive else folder.iterdir()
    guids: list[str] = []
    for p in it:
        if not p.is_file():
            continue
        if p.suffix.lower() not in _MEDIA_EXTS:
            continue
        try:
            g = ingest_file(
                p,
                show_slug=slug,
                state=state,
                watchlist_path=watchlist_path,
                source="local-folder",
                max_duration_hours=max_duration_hours,
            )
            guids.append(g)
        except IngestError as e:
            logger.info("skip %s: %s", p, e)
    return guids


def _yt_dlp_probe(url: str) -> dict:
    """Probe ``url`` with ``yt-dlp --dump-single-json -s``.

    Returns the metadata dict (id / uploader / title / upload_date /
    duration). Kept as a module-level function so tests can
    monkey-patch it without spawning yt-dlp.
    """
    from core.ytdlp import ytdlp_path

    r = subprocess.run(
        [str(ytdlp_path()), "--dump-single-json", "-s", "--no-warnings", url],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0 or not r.stdout:
        raise IngestError(f"yt-dlp could not probe {url!r}: {r.stderr.strip()[:200]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise IngestError(f"yt-dlp returned non-JSON for {url!r}: {e}") from e


def ingest_url(
    url: str,
    *,
    show_slug: str | None,
    state: StateStore,
    watchlist_path: Path,
) -> str:
    """Ingest a pasted URL via yt-dlp's generic extractor. Returns the
    episode GUID (``<Extractor>:<id>``). Actual audio download happens
    later in the pipeline's URL branch.

    YouTube watch URLs are detected via the yt-dlp extractor name
    (``youtube`` family) and the show is created with
    ``source="youtube"`` so the existing captions-first / whisper
    fallback pipeline picks them up. Pre-2026-04-27 these landed under
    ``source="url"`` and were sent through the podcast download path,
    which fetched the watch HTML and rejected it as
    ``Content-Type: text/html``.
    """
    info = _yt_dlp_probe(url)
    vid_id = info.get("id") or ""
    extractor = info.get("extractor") or "generic"
    uploader = info.get("uploader")
    slug = show_slug or slug_for_url(url, uploader=uploader)

    # YouTube extractor names start with "youtube" (e.g. "youtube",
    # "youtube:tab", "youtube:playlist"). Route them through the YouTube
    # pipeline by tagging the show as a YouTube source.
    is_youtube = extractor.lower().startswith("youtube")
    show_source = "youtube" if is_youtube else "url"

    _ensure_show(
        slug,
        source=show_source,
        title=uploader or slug,
        watchlist_path=watchlist_path,
    )

    guid = f"{extractor}:{vid_id}" if vid_id else url
    state.upsert_episode(
        show_slug=slug,
        guid=guid,
        title=info.get("title") or url,
        pub_date=_format_upload_date(info.get("upload_date") or ""),
        mp3_url=url,
        duration_sec=info.get("duration") or None,
    )
    return guid
