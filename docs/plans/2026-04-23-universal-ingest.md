# Universal Ingest Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend Paragraphos's ingest surface beyond RSS podcasts and YouTube channels to any audio/video source the user has — via drag-drop of files, pasted URLs, a watched folder, or one-shot folder import.

**Architecture:** Three entry points funnel into the existing `shows → episodes` model through synthetic shows. A new `core/local_source.py` owns ingest helpers (`sha256_of`, slug derivation, ffprobe gates, `ingest_file` / `ingest_folder` / `ingest_url`). `core/watch_folder.py` wraps `watchdog.Observer` mirroring the existing `core/library.py` pattern. A new pipeline branch (`_process_local_episode`, dispatched on `ctx.source == "local"`) bypasses `download_mp3` — source files are copy-or-symlinked into staging, then the existing `transcribe_episode` path runs unchanged. URL ingest reuses the v1.2.0 yt-dlp generic-extractor plumbing.

**Tech Stack:** Python 3.12, PyQt6 6.7, watchdog 4.x, ffprobe (ships with ffmpeg, already a declared dep), yt-dlp (lazy-installed since v1.2.0), pytest + `QT_QPA_PLATFORM=offscreen` for UI smokes.

**Design doc:** `docs/plans/2026-04-23-universal-ingest-design.md`.

**Working branch:** `ship-v1` (continue linear history; tag v1.3.0 once all tasks land).

**Related skills:**
- @superpowers:test-driven-development
- @superpowers:verification-before-completion
- @superpowers:requesting-code-review

---

## Conventions for this plan

- Every step runs from `~/dev/paragraphos/`.
- Python is invoked as `.venv/bin/python` (project venv; already set up).
- Tests are pytest: `.venv/bin/python -m pytest tests/<file> -v` for targeted, `.venv/bin/python -m pytest -q` for full suite.
- UI smoke tests need `QT_QPA_PLATFORM=offscreen` prepended.
- Each numbered Task ends with one commit. Follow the repo's Conventional-Commits style (match recent log entries: `feat(scope): …`, `fix(scope): …`, `test(scope): …`, `docs(…): …`).
- Never skip a failing test with `--no-verify`. If pre-commit fails, fix the underlying issue.

---

## Task 1: Extend `Show.source` values + add `Settings` local-source fields

Broaden the source discriminator and add the config surface the watch-folder + duration cap features read from.

**Files:**
- Modify: `core/models.py` — `Show.source` doc comment (no validator change needed; field is `str`); add four `Settings` fields.
- Test: `tests/test_models.py` (extend).

**Step 1: Failing test for new Show.source values + Settings fields.**

Append to `tests/test_models.py`:

```python
def test_show_source_accepts_local_variants():
    from core.models import Show
    for src in ("local-folder", "local-drop", "url"):
        s = Show(slug="x", title="X", rss="", source=src)
        assert s.source == src


def test_settings_has_local_source_defaults():
    from core.models import Settings
    s = Settings()
    assert s.watch_folder_enabled is False
    assert s.watch_folder_root == "~/Paragraphos/to-be-transcribed"
    assert s.watch_folder_post == "keep"  # keep | move | delete
    assert s.local_max_duration_hours == 4
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_models.py -k "local" -v`
Expected: FAIL — `watch_folder_enabled` missing on `Settings`. (The `Show.source` test already passes because the field is free-form `str`; leave it in for guardrail.)

**Step 3: Add fields.**

Edit `core/models.py`, inside `class Settings` after the `auto_resume_failed_window_hours` line:

```python
    # Local source ingest (v1.3.0 "universal ingest").
    #
    # ``watch_folder_root`` is expanded via ``Path.expanduser()``; a fresh
    # install keeps the feature off (``enabled=False``) until the user
    # opts in via Settings → Local sources. ``post`` chooses what happens
    # to a watched file after its episode transitions to ``done``:
    # ``keep`` leaves it in place (default, safest), ``move`` relocates it
    # to a sibling ``done/`` folder mirroring any subfolder path, and
    # ``delete`` unlinks it. ``local_max_duration_hours`` gates any ingest
    # (drop, watch, folder-import) — files exceeding it go to Failed with
    # a clear reason. 4 h covers long lectures and most board-meeting
    # recordings without letting an accidentally-queued movie consume a
    # whole afternoon of whisper time.
    watch_folder_enabled: bool = False
    watch_folder_root: str = "~/Paragraphos/to-be-transcribed"
    watch_folder_post: str = "keep"
    local_max_duration_hours: int = 4
```

Also update the `Show.source` comment to list the new values. Find:

```python
    # Source discriminator: "podcast" (RSS feed) or "youtube" (channel
    # RSS at /feeds/videos.xml?channel_id=UC...). Defaults to "podcast"
    # for backward compat with existing watchlist.yaml files.
    source: str = "podcast"
```

Replace with:

```python
    # Source discriminator. Values:
    #   podcast       — RSS feed
    #   youtube       — channel RSS at /feeds/videos.xml?channel_id=UC...
    #   local-folder  — a watched folder on disk (rss empty; path in meta)
    #   local-drop    — drag-drop / Import folder one-offs (rss empty)
    #   url           — ad-hoc URL ingest via yt-dlp generic extractor
    # Defaults to "podcast" for backward compat with existing
    # watchlist.yaml files.
    source: str = "podcast"
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_models.py -k "local or source" -v`
Expected: PASS.

**Step 5: Full suite.**

Run: `.venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit.**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat(models): local-source values on Show.source + watch-folder Settings"
```

---

## Task 2: `core/local_source.py` skeleton + `sha256_of` with mtime/size cache

Content-hash helper used as GUID basis for local files. The cache matters: SHA-256 of a 1 GB file takes ~2 s; re-ingesting an unchanged path must skip that.

**Files:**
- Create: `core/local_source.py`.
- Test: `tests/test_local_source.py` (new).

**Step 1: Failing test.**

Create `tests/test_local_source.py`:

```python
"""Tests for core/local_source.py — file hashing + slug derivation + ingest."""

from __future__ import annotations

from pathlib import Path

from core.state import StateStore


def _fresh_state(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "s.sqlite")
    s.init_schema()
    return s


def test_sha256_of_hashes_small_file(tmp_path: Path):
    from core.local_source import sha256_of

    f = tmp_path / "a.wav"
    f.write_bytes(b"hello")
    state = _fresh_state(tmp_path)

    h = sha256_of(f, state=state)
    # SHA-256 of b"hello"
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_sha256_of_caches_by_mtime_size(tmp_path: Path):
    from core import local_source
    from core.local_source import sha256_of

    f = tmp_path / "a.wav"
    f.write_bytes(b"hello")
    state = _fresh_state(tmp_path)

    first = sha256_of(f, state=state)

    # Second call must not re-hash. Monkey-patch hashlib.sha256 to blow up
    # if invoked; the cache hit path must not touch it.
    called = {"n": 0}
    import hashlib

    real = hashlib.sha256

    def exploding_sha256(*a, **kw):
        called["n"] += 1
        return real(*a, **kw)

    local_source._hashlib_sha256 = exploding_sha256  # type: ignore[attr-defined]
    second = sha256_of(f, state=state)
    assert second == first
    assert called["n"] == 0


def test_sha256_of_rehashes_when_mtime_changes(tmp_path: Path):
    import os
    import time

    from core.local_source import sha256_of

    f = tmp_path / "a.wav"
    f.write_bytes(b"hello")
    state = _fresh_state(tmp_path)
    sha256_of(f, state=state)

    time.sleep(0.01)
    f.write_bytes(b"world")
    # bump mtime explicitly in case the FS resolution elided it
    now = time.time() + 1
    os.utime(f, (now, now))

    h2 = sha256_of(f, state=state)
    # SHA-256 of b"world"
    assert h2 == "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7"
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: FAIL — `core.local_source` not importable.

**Step 3: Implement.**

Create `core/local_source.py`:

```python
"""Universal-ingest helpers: local files, folders, and arbitrary URLs.

Three entry points (drop zone, watch folder, folder import) funnel into
the existing ``shows → episodes`` model via synthetic shows. See
``docs/plans/2026-04-23-universal-ingest-design.md``.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

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
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: all three tests PASS.

**Step 5: Commit.**

```bash
git add core/local_source.py tests/test_local_source.py
git commit -m "feat(local-source): sha256_of with mtime+size cache in state.meta"
```

---

## Task 3: Show-slug derivation helpers

Four helpers, one per ingest path. Keep them small and pure — they must be trivially testable without the filesystem or network.

**Files:**
- Modify: `core/local_source.py`.
- Test: `tests/test_local_source.py` (extend).

**Step 1: Failing test.**

Append to `tests/test_local_source.py`:

```python
def test_slug_for_drop_default():
    from core.local_source import slug_for_drop
    assert slug_for_drop() == "files"


def test_slug_for_watch_uses_top_level_subfolder(tmp_path: Path):
    from core.local_source import slug_for_watch

    root = tmp_path / "to-be-transcribed"
    root.mkdir()
    (root / "Zoom Meetings").mkdir()
    f = root / "Zoom Meetings" / "team-standup.mp4"
    f.write_bytes(b"")
    assert slug_for_watch(f, root) == "zoom-meetings"


def test_slug_for_watch_falls_back_when_at_root(tmp_path: Path):
    from core.local_source import slug_for_watch

    root = tmp_path / "to-be-transcribed"
    root.mkdir()
    f = root / "loose.wav"
    f.write_bytes(b"")
    assert slug_for_watch(f, root) == "files"


def test_slug_for_folder_import_uses_basename(tmp_path: Path):
    from core.local_source import slug_for_folder_import

    p = tmp_path / "My Field Interviews"
    p.mkdir()
    assert slug_for_folder_import(p, override=None) == "my-field-interviews"


def test_slug_for_folder_import_honours_override(tmp_path: Path):
    from core.local_source import slug_for_folder_import

    p = tmp_path / "whatever"
    p.mkdir()
    assert slug_for_folder_import(p, override="interviews-2026") == "interviews-2026"


def test_slug_for_url_uses_uploader_when_available():
    from core.local_source import slug_for_url

    assert slug_for_url("https://vimeo.com/12345", uploader="Acme Films") == "acme-films"
    assert slug_for_url("https://example.com/x", uploader="") == "web"
    assert slug_for_url("https://example.com/x", uploader=None) == "web"
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: the five new tests FAIL (ImportError).

**Step 3: Implement.**

Append to `core/local_source.py`:

```python
from core.sanitize import slugify


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
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: all tests PASS.

**Step 5: Commit.**

```bash
git add core/local_source.py tests/test_local_source.py
git commit -m "feat(local-source): show-slug derivation for drop/watch/folder/url"
```

---

## Task 4: ffprobe helpers — audio-stream check + duration

whisper can't transcribe a file with no audio. We gate every ingest with an `ffprobe` call; `ffmpeg` (which ships `ffprobe`) is already a declared dep and discovered by `core/transcriber._locate_ffmpeg_dir`.

**Files:**
- Modify: `core/local_source.py`.
- Test: `tests/test_local_source.py` (extend).

**Step 1: Failing test.**

Append to `tests/test_local_source.py`:

```python
def test_has_audio_stream_true_for_audio_file(monkeypatch):
    from core import local_source

    def fake_run(args, **kw):
        class R:
            returncode = 0
            stdout = '{"streams":[{"codec_type":"audio","codec_name":"aac"}]}'
            stderr = ""
        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_run)
    assert local_source.has_audio_stream(Path("/nonexistent.mp4")) is True


def test_has_audio_stream_false_for_silent_video(monkeypatch):
    from core import local_source

    def fake_run(args, **kw):
        class R:
            returncode = 0
            stdout = '{"streams":[{"codec_type":"video","codec_name":"h264"}]}'
            stderr = ""
        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_run)
    assert local_source.has_audio_stream(Path("/nonexistent.mp4")) is False


def test_has_audio_stream_false_on_ffprobe_failure(monkeypatch):
    from core import local_source

    def fake_run(args, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = "Invalid data found"
        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_run)
    assert local_source.has_audio_stream(Path("/nonexistent.mp4")) is False


def test_duration_seconds_reads_format_duration(monkeypatch):
    from core import local_source

    def fake_run(args, **kw):
        class R:
            returncode = 0
            stdout = '{"format":{"duration":"183.42"}}'
            stderr = ""
        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_run)
    assert local_source.duration_seconds(Path("/nonexistent.mp4")) == 183


def test_duration_seconds_returns_none_on_failure(monkeypatch):
    from core import local_source

    def fake_run(args, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_run)
    assert local_source.duration_seconds(Path("/nonexistent.mp4")) is None
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: new tests FAIL (AttributeError on `subprocess` / helpers).

**Step 3: Implement.**

Append to `core/local_source.py`:

```python
import json
import shutil
import subprocess


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
                "-v", "error",
                "-show_streams",
                "-of", "json",
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
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
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
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: PASS.

**Step 5: Commit.**

```bash
git add core/local_source.py tests/test_local_source.py
git commit -m "feat(local-source): ffprobe helpers (has_audio_stream + duration_seconds)"
```

---

## Task 5: `ingest_file` / `ingest_folder` / `ingest_url` + synthetic-show upsert

Entry points the UI and CLI call. Each returns a list of ingested episode GUIDs so the caller can report / chain.

**Files:**
- Modify: `core/local_source.py`.
- Test: `tests/test_local_source.py` (extend).

**Step 1: Failing test.**

Append to `tests/test_local_source.py`:

```python
def _seed_watchlist(tmp_path: Path):
    from core.models import Watchlist
    wl = Watchlist()
    wl_path = tmp_path / "watchlist.yaml"
    wl.save(wl_path)
    return wl_path


def test_ingest_file_creates_synthetic_show_and_episode(tmp_path: Path):
    from core import local_source
    from core.local_source import ingest_file
    from core.models import Watchlist

    f = tmp_path / "a.wav"
    f.write_bytes(b"hello")
    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    # ffprobe returns audio + a 42-s duration
    def fake_has_audio(_p):
        return True

    def fake_duration(_p):
        return 42

    local_source.has_audio_stream = fake_has_audio  # type: ignore[assignment]
    local_source.duration_seconds = fake_duration  # type: ignore[assignment]

    guid = ingest_file(f, show_slug=None, state=state, watchlist_path=wl_path)

    # GUID is sha256:<hex>
    assert guid.startswith("sha256:")

    # Synthetic show created
    wl = Watchlist.load(wl_path)
    slugs = [s.slug for s in wl.shows]
    assert "files" in slugs
    show = next(s for s in wl.shows if s.slug == "files")
    assert show.source == "local-drop"

    # Episode row persisted
    ep = state.get_episode(guid)
    assert ep is not None
    assert ep["show_slug"] == "files"
    assert ep["duration_sec"] == 42
    assert ep["status"] == "pending"


def test_ingest_file_rejects_video_without_audio(tmp_path: Path):
    from core import local_source
    from core.local_source import IngestError, ingest_file

    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    local_source.has_audio_stream = lambda p: False  # type: ignore[assignment]
    local_source.duration_seconds = lambda p: None  # type: ignore[assignment]

    import pytest
    with pytest.raises(IngestError, match="no audio"):
        ingest_file(f, show_slug=None, state=state, watchlist_path=wl_path)


def test_ingest_file_rejects_over_duration_cap(tmp_path: Path):
    from core import local_source
    from core.local_source import IngestError, ingest_file

    f = tmp_path / "big.mp4"
    f.write_bytes(b"x")
    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    local_source.has_audio_stream = lambda p: True  # type: ignore[assignment]
    # 5 hours
    local_source.duration_seconds = lambda p: 5 * 3600  # type: ignore[assignment]

    import pytest
    with pytest.raises(IngestError, match="duration cap"):
        ingest_file(f, show_slug=None, state=state, watchlist_path=wl_path, max_duration_hours=4)


def test_ingest_folder_recursive(tmp_path: Path):
    from core import local_source
    from core.local_source import ingest_folder

    root = tmp_path / "field"
    (root / "2026-01").mkdir(parents=True)
    (root / "2026-01" / "a.wav").write_bytes(b"a")
    (root / "b.wav").write_bytes(b"b")
    # A non-media file that must be skipped
    (root / "notes.txt").write_bytes(b"x")

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    local_source.has_audio_stream = lambda p: True  # type: ignore[assignment]
    local_source.duration_seconds = lambda p: 30  # type: ignore[assignment]

    guids = ingest_folder(
        root, show_slug=None, state=state, watchlist_path=wl_path, recursive=True
    )
    assert len(guids) == 2
    from core.models import Watchlist
    wl = Watchlist.load(wl_path)
    assert any(s.slug == "field" and s.source == "local-folder" for s in wl.shows)


def test_ingest_url_dispatches_through_yt_dlp(tmp_path: Path, monkeypatch):
    from core import local_source
    from core.local_source import ingest_url

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    # Fake yt-dlp metadata probe
    monkeypatch.setattr(
        local_source,
        "_yt_dlp_probe",
        lambda url: {
            "id": "abc123",
            "extractor": "Vimeo",
            "uploader": "Acme Films",
            "title": "Annual Talk",
            "upload_date": "20260301",
            "duration": 1234,
        },
    )

    guid = ingest_url("https://vimeo.com/12345", show_slug=None, state=state, watchlist_path=wl_path)
    assert guid == "Vimeo:abc123"

    from core.models import Watchlist
    wl = Watchlist.load(wl_path)
    show = next(s for s in wl.shows if s.slug == "acme-films")
    assert show.source == "url"

    ep = state.get_episode(guid)
    assert ep is not None
    assert ep["title"] == "Annual Talk"
    assert ep["pub_date"] == "2026-03-01"
    assert ep["duration_sec"] == 1234
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: new tests FAIL (ImportError on `ingest_file` etc.).

**Step 3: Implement.**

Append to `core/local_source.py`:

```python
from datetime import date, datetime, timezone

from core.models import Show, Watchlist

# Extensions ffmpeg handles on the audio-extract path. We gate on this
# set rather than asking ffprobe blindly on every file in a directory
# scan — keeps a folder-import of a mixed directory cheap.
_MEDIA_EXTS = frozenset({
    ".mp3", ".m4a", ".m4b", ".wav", ".aiff", ".aif", ".flac",
    ".ogg", ".oga", ".opus",
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv",
})


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
    wl.shows.append(Show(
        slug=slug,
        title=title,
        rss="",  # synthetic shows have no feed
        source=source,
        enabled=True,
        whisper_prompt="",
        language="",  # inherit default
    ))
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
        mp3_url=f"file://{p}",
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
    from core.ytdlp import ytdlp_bin

    r = subprocess.run(
        [ytdlp_bin(), "--dump-single-json", "-s", "--no-warnings", url],
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
    """
    info = _yt_dlp_probe(url)
    vid_id = info.get("id") or ""
    extractor = info.get("extractor") or "generic"
    uploader = info.get("uploader")
    slug = show_slug or slug_for_url(url, uploader=uploader)

    _ensure_show(
        slug,
        source="url",
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
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: all PASS.

**Step 5: Commit.**

```bash
git add core/local_source.py tests/test_local_source.py
git commit -m "feat(local-source): ingest_file / ingest_folder / ingest_url"
```

---

## Task 6: Pipeline `_process_local_episode` branch

Bypass `download_mp3` when `ctx.source == "local"`. The source file is copied-or-symlinked into the staging `audio/` folder under the show's output directory, then the existing `transcribe_episode` path runs unchanged.

**Files:**
- Modify: `core/pipeline.py`.
- Test: `tests/test_pipeline_local.py` (new).

**Step 1: Failing test.**

Create `tests/test_pipeline_local.py`:

```python
"""Pipeline integration for local-source shows."""

from pathlib import Path
from unittest.mock import patch

from core.library import LibraryIndex
from core.pipeline import PipelineContext, process_episode
from core.state import StateStore


def _local_ctx(tmp_path: Path) -> PipelineContext:
    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    out = tmp_path / "out"
    out.mkdir()
    lib = LibraryIndex(out)
    return PipelineContext(
        state=state,
        library=lib,
        output_root=out,
        whisper_prompt="",
        retention_days=7,
        delete_mp3_after=False,
        source="local",
    )


def _seed_local_episode(ctx: PipelineContext, src: Path, *, guid: str = "sha256:deadbeef") -> None:
    ctx.state.upsert_episode(
        show_slug="files",
        guid=guid,
        title=src.stem,
        pub_date="2026-04-15",
        mp3_url=f"file://{src}",
        duration_sec=42,
    )
    ctx.state.set_meta(f"local_path:{guid}", str(src))


def test_local_episode_copies_source_and_transcribes(tmp_path: Path):
    src = tmp_path / "a.wav"
    src.write_bytes(b"fake wav bytes")

    ctx = _local_ctx(tmp_path)
    _seed_local_episode(ctx, src)

    class FakeResult:
        md_path = tmp_path / "out" / "files" / "x.md"
        srt_path = tmp_path / "out" / "files" / "x.srt"
        word_count = 10

    def fake_transcribe(*a, **kw):
        FakeResult.md_path.parent.mkdir(parents=True, exist_ok=True)
        FakeResult.md_path.write_text("# x\n\nhello", encoding="utf-8")
        FakeResult.srt_path.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8"
        )
        return FakeResult

    with patch("core.pipeline.transcribe_episode", side_effect=fake_transcribe):
        r = process_episode("sha256:deadbeef", ctx)

    assert r.action == "transcribed"
    assert ctx.state.get_episode("sha256:deadbeef")["status"] == "done"
    # Source file must still exist (delete_mp3_after=False above).
    assert src.exists()


def test_local_episode_fails_gracefully_when_source_missing(tmp_path: Path):
    src = tmp_path / "gone.wav"
    ctx = _local_ctx(tmp_path)
    _seed_local_episode(ctx, src, guid="sha256:missing")

    r = process_episode("sha256:missing", ctx)
    assert r.action == "failed"
    assert "source file" in r.detail.lower()
    assert ctx.state.get_episode("sha256:missing")["status"] == "failed"
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_pipeline_local.py -v`
Expected: FAIL — `process_episode` routes everything through the podcast path, source file never materialised.

**Step 3: Implement.**

Edit `core/pipeline.py`. In `process_episode`, just below the YouTube dispatch, add a local branch:

```python
def process_episode(
    guid: str, ctx: PipelineContext, *, episode_number: str = "0000"
) -> PipelineResult:
    """Serial dedup → download → transcribe → retention (kept for CLI/tests)."""
    if ctx.source == "youtube":
        return _process_youtube_episode(guid, ctx, episode_number=episode_number)
    if ctx.source == "local":
        return _process_local_episode(guid, ctx, episode_number=episode_number)
    outcome = download_phase(guid, ctx, episode_number=episode_number)
    if outcome.result is not None:
        return outcome.result
    return transcribe_phase(outcome, ctx)
```

Append a new function to the same file (above `_process_youtube_episode` for locality):

```python
def _process_local_episode(
    guid: str, ctx: PipelineContext, *, episode_number: str = "0000"
) -> PipelineResult:
    """Local-source branch: dedup → copy/symlink → whisper → retention.

    The source file's absolute path was persisted at ingest time under
    ``state.meta["local_path:<guid>"]``. We materialise it into the
    show's staging ``audio/`` directory (copy for robustness — symlink
    would break on external-drive unmounts later) and then reuse the
    existing :func:`transcribe_phase` machinery by forging a
    ``DownloadOutcome``.
    """
    import shutil as _shutil

    from core.security import safe_path_within

    ep = ctx.state.get_episode(guid)
    if ep is None:
        raise ValueError(f"unknown guid {guid}")

    slug = build_slug(ep["pub_date"], ep["title"], episode_number)

    dup = ctx.library.check_dedup(guid=guid, filename_key=slug)
    if dup.matched:
        ctx.state.set_status(guid, EpisodeStatus.DONE)
        return PipelineResult("skipped", guid, f"dedup/{dup.reason} → {dup.path}")

    src_path_str = ctx.state.get_meta(f"local_path:{guid}") or ""
    if not src_path_str:
        err = "local ingest: missing local_path meta"
        ctx.state.set_status(guid, EpisodeStatus.FAILED, error_text=err)
        return PipelineResult("failed", guid, err)
    src = Path(src_path_str)
    if not src.exists():
        err = f"local ingest: source file missing on disk: {src}"
        ctx.state.set_status(guid, EpisodeStatus.FAILED, error_text=err)
        return PipelineResult("failed", guid, err)

    show_dir = ctx.output_root / ep["show_slug"]
    audio_dir = show_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    # Preserve the user's extension so whisper-cli routes the right
    # ffmpeg demuxer. build_slug's .mp3 suffix in the podcast path was
    # an accident of history; for local we keep the real extension.
    staged = audio_dir / f"{slug}{src.suffix}"
    safe_path_within(ctx.output_root, staged)
    safe_path_within(ctx.output_root, show_dir / f"{slug}.md")
    try:
        _guard_disk(audio_dir)
        ctx.state.set_status(guid, EpisodeStatus.DOWNLOADING)
        _shutil.copy2(src, staged)
    except DiskSpaceError as e:
        ctx.state.set_status(guid, EpisodeStatus.PENDING)
        return PipelineResult("failed", guid, f"disk: {e}")
    except OSError as e:
        err = f"local ingest: copy failed [{type(e).__name__}]: {e}"
        ctx.state.set_status(guid, EpisodeStatus.FAILED, error_text=err)
        return PipelineResult("failed", guid, err)
    ctx.state.set_status(guid, EpisodeStatus.DOWNLOADED)

    # Hand off to the existing transcribe machinery via a forged outcome.
    outcome = DownloadOutcome(
        guid=guid,
        mp3_path=staged,
        show_dir=show_dir,
        slug=slug,
        ep=ep,
    )
    return transcribe_phase(outcome, ctx)
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_pipeline_local.py -v`
Expected: PASS.

**Step 5: Full suite.**

Run: `.venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit.**

```bash
git add core/pipeline.py tests/test_pipeline_local.py
git commit -m "feat(pipeline): local-source branch (copy-to-staging + whisper)"
```

---

## Task 7: `core/watch_folder.py` — WatchFolder wrapping `watchdog.Observer`

Mirrors `core/library.start_watching`. 2 s debounce (files may still be writing when the first event fires), ffprobe gate, retry-once-at-5 s, pause-on-root-disappearance.

**Files:**
- Create: `core/watch_folder.py`.
- Test: `tests/test_watch_folder.py` (new).

**Step 1: Failing test.**

Create `tests/test_watch_folder.py`:

```python
"""Tests for core/watch_folder.py — debounce, ffprobe gate, disappearance handling."""

from pathlib import Path

from core.state import StateStore


def _fresh_state(tmp_path: Path) -> StateStore:
    s = StateStore(tmp_path / "s.sqlite")
    s.init_schema()
    return s


def _seed_watchlist(tmp_path: Path):
    from core.models import Watchlist
    wl = Watchlist()
    p = tmp_path / "watchlist.yaml"
    wl.save(p)
    return p


def test_watch_folder_ingests_new_file_after_debounce(tmp_path: Path, monkeypatch):
    from core import local_source, watch_folder

    root = tmp_path / "watch"
    root.mkdir()
    (root / "zoom").mkdir()

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    monkeypatch.setattr(local_source, "has_audio_stream", lambda p: True)
    monkeypatch.setattr(local_source, "duration_seconds", lambda p: 60)

    # 0 s debounce so the test doesn't wait
    wf = watch_folder.WatchFolder(
        root=root, state=state, watchlist_path=wl_path, debounce_seconds=0.0
    )
    wf.start()
    try:
        f = root / "zoom" / "standup.mp4"
        f.write_bytes(b"x")
        # Poll up to 3 s for the ingest to land
        import time
        deadline = time.time() + 3.0
        ep = None
        while time.time() < deadline:
            with state._conn() as c:
                row = c.execute(
                    "SELECT * FROM episodes WHERE show_slug='zoom' LIMIT 1"
                ).fetchone()
            if row:
                ep = dict(row)
                break
            time.sleep(0.05)
        assert ep is not None
        assert ep["status"] == "pending"
    finally:
        wf.stop()


def test_watch_folder_pauses_on_root_disappearance(tmp_path: Path):
    from core.watch_folder import WatchFolder

    root = tmp_path / "gone"
    # do NOT mkdir — simulate a never-existing / unmounted root

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    wf = WatchFolder(root=root, state=state, watchlist_path=wl_path, debounce_seconds=0.0)
    wf.start()
    try:
        # Non-existent root should mark paused
        assert wf.is_paused()
    finally:
        wf.stop()
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_watch_folder.py -v`
Expected: FAIL — `core.watch_folder` missing.

**Step 3: Implement.**

Create `core/watch_folder.py`:

```python
"""Watchdog-backed folder observer for the v1.3 universal-ingest feature.

Mirrors ``core.library.start_watching`` in shape. On every new file
event we:

  1. Skip non-media extensions (cheap ``_MEDIA_EXTS`` check).
  2. Debounce ``debounce_seconds`` so a file mid-write finishes before
     ffprobe looks at it.
  3. ffprobe the file; retry once after 5 s if it fails (e.g. the file
     is still being written by a slow exporter).
  4. Call :func:`core.local_source.ingest_file` with the watched root's
     ``slug_for_watch`` derivation.

If the watch root doesn't exist at start() time, the observer marks
itself paused (``is_paused()``) and emits nothing until start() is
called again on a now-existing path.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from core.local_source import (
    IngestError,
    _MEDIA_EXTS,
    has_audio_stream,
    ingest_file,
    slug_for_watch,
)
from core.state import StateStore

logger = logging.getLogger(__name__)


class WatchFolder:
    """Background watchdog on a user-chosen folder root."""

    def __init__(
        self,
        *,
        root: Path,
        state: StateStore,
        watchlist_path: Path,
        debounce_seconds: float = 2.0,
        max_duration_hours: int = 4,
    ) -> None:
        self.root = Path(root).expanduser()
        self.state = state
        self.watchlist_path = watchlist_path
        self.debounce_seconds = debounce_seconds
        self.max_duration_hours = max_duration_hours
        self._observer = None  # type: ignore[assignment]
        self._paused = False

    def is_paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        if not self.root.exists():
            logger.warning("watch root does not exist: %s — paused", self.root)
            self._paused = True
            return
        self._paused = False

        handler_self = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                p = Path(event.src_path)
                if p.suffix.lower() not in _MEDIA_EXTS:
                    return
                threading.Thread(
                    target=handler_self._handle_new_file,
                    args=(p,),
                    name="wf-ingest",
                    daemon=True,
                ).start()

        obs = Observer()
        obs.schedule(_Handler(), str(self.root), recursive=True)
        obs.start()
        self._observer = obs

    def stop(self) -> None:
        obs = self._observer
        self._observer = None
        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=2.0)
            except Exception:
                pass

    def _handle_new_file(self, p: Path) -> None:
        """Debounce + ffprobe gate + ingest_file."""
        time.sleep(self.debounce_seconds)
        if not has_audio_stream(p):
            # Writer may still be flushing the container; retry once.
            time.sleep(5.0)
            if not has_audio_stream(p):
                logger.info("watch: skipping %s — no audio stream (post-retry)", p)
                return

        slug = slug_for_watch(p, self.root)
        try:
            guid = ingest_file(
                p,
                show_slug=slug,
                state=self.state,
                watchlist_path=self.watchlist_path,
                source="local-folder",
                max_duration_hours=self.max_duration_hours,
            )
            logger.info("watch: queued %s → %s (%s)", p.name, slug, guid)
        except IngestError as e:
            logger.warning("watch: skip %s: %s", p, e)
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_watch_folder.py -v`
Expected: PASS. (The first test can take ~0.5-3 s; watchdog fires asynchronously.)

**Step 5: Full suite.**

Run: `.venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit.**

```bash
git add core/watch_folder.py tests/test_watch_folder.py
git commit -m "feat(watch-folder): watchdog-backed local-source observer"
```

---

## Task 8: Settings UI — Local sources group

Expose the four new Settings fields in the pane.

**Files:**
- Modify: `ui/settings_pane.py`.
- Test: `tests/test_settings_pane_local.py` (new — smoke construct).

**Step 1: Failing smoke test.**

Create `tests/test_settings_pane_local.py`:

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_settings_pane_has_local_sources_group(qtbot, tmp_path):  # noqa: ARG001
    import PyQt6.QtWidgets as qtw

    app = qtw.QApplication.instance() or qtw.QApplication([])

    from core.models import Settings
    from ui.settings_pane import SettingsPane

    s = Settings()
    s.save(tmp_path / "settings.yaml")

    pane = SettingsPane(settings=s, settings_path=tmp_path / "settings.yaml")
    # Simple discoverability assertion: the pane's text contains the
    # group heading. Robust to layout refactors.
    text = pane.findChildren(qtw.QLabel)
    assert any("Local sources" in (lab.text() or "") for lab in text)
```

`qtbot` requires `pytest-qt`. If not installed, adjust to a plain `QApplication.instance()` check — the existing `test_queue_hero.py` / `test_first_run_wizard.py` already follow this pattern; mirror whichever is in use.

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_settings_pane_local.py -v`
Expected: FAIL — no "Local sources" group yet.

**Step 3: Implement.**

Edit `ui/settings_pane.py`. Locate the block that builds the Sources group (added in v1.2.0). Just after that block — before the block that saves on change — insert a new group, following the existing `_section("Local sources")` pattern:

```python
        local = self._section("Local sources")
        self._add_field(
            "Watch folder",
            self._toggle("watch_folder_enabled"),
            hint="Auto-queue files dropped into the folder below.",
        )
        self._add_field(
            "Folder path",
            self._path_picker("watch_folder_root"),
            hint="Top-level subfolders become shows.",
        )
        self._add_field(
            "After transcribing",
            self._combo(
                "watch_folder_post",
                [("keep", "Keep in place"), ("move", "Move to done/"), ("delete", "Delete")],
            ),
            hint="What to do with each file once its transcript is written.",
        )
        self._add_field(
            "Max duration (hours)",
            self._spin("local_max_duration_hours", 1, 48),
            hint="Files longer than this go to Failed instead of transcribing.",
        )
        local.addStretch(1)
```

If helpers `_toggle`, `_path_picker`, `_combo`, `_spin` don't exist by these names, reuse whatever analogous method the Sources or Obsidian group already uses in the same file — grep for how `sources_podcasts`, `obsidian_vault_path`, `mp3_retention_days`, and `notify_mode` are wired.

**Step 4: Verify pass.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_settings_pane_local.py -v`
Expected: PASS.

**Step 5: Full suite.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit.**

```bash
git add ui/settings_pane.py tests/test_settings_pane_local.py
git commit -m "feat(settings): Local sources group (watch folder + max duration)"
```

---

## Task 9: `ui/drop_zone.py` — Shows-page card + global main-window drop handler

Discoverable drop target with URL input; plus a catch-all handler so a drop anywhere on the main window dispatches to the same code.

**Files:**
- Create: `ui/drop_zone.py`.
- Modify: `ui/main_window.py` (install DropZone on Shows page + global drop handler).
- Test: `tests/test_drop_zone.py` (new).

**Step 1: Failing smoke test.**

Create `tests/test_drop_zone.py`:

```python
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_drop_zone_accepts_file_uri(tmp_path: Path, monkeypatch):
    import PyQt6.QtWidgets as qtw

    _ = qtw.QApplication.instance() or qtw.QApplication([])

    from core.state import StateStore
    from ui.drop_zone import DropZone

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    from core.models import Watchlist
    (tmp_path / "watchlist.yaml").write_text("shows: []\n", encoding="utf-8")

    captured = {}

    def fake_ingest_file(path, **kw):
        captured["path"] = Path(path)
        return "sha256:fake"

    monkeypatch.setattr("ui.drop_zone.ingest_file", fake_ingest_file)

    dz = DropZone(
        state=state,
        watchlist_path=tmp_path / "watchlist.yaml",
        max_duration_hours=4,
    )
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    dz.handle_paths([f])
    assert captured["path"] == f


def test_drop_zone_accepts_url_text(tmp_path: Path, monkeypatch):
    import PyQt6.QtWidgets as qtw

    _ = qtw.QApplication.instance() or qtw.QApplication([])

    from core.state import StateStore
    from ui.drop_zone import DropZone

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    (tmp_path / "watchlist.yaml").write_text("shows: []\n", encoding="utf-8")

    captured = {}

    def fake_ingest_url(url, **kw):
        captured["url"] = url
        return "Vimeo:abc"

    monkeypatch.setattr("ui.drop_zone.ingest_url", fake_ingest_url)

    dz = DropZone(
        state=state,
        watchlist_path=tmp_path / "watchlist.yaml",
        max_duration_hours=4,
    )
    dz.handle_url("https://vimeo.com/42")
    assert captured["url"] == "https://vimeo.com/42"
```

**Step 2: Verify fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_drop_zone.py -v`
Expected: FAIL — `ui.drop_zone` missing.

**Step 3: Implement.**

Create `ui/drop_zone.py`:

```python
"""Drop-target widget for the v1.3 universal-ingest feature.

A card on the Shows page shows the prompt and hosts the URL input. It
doubles as a dispatcher for the main window's global ``dropEvent`` so
a user can drag a file anywhere and it still works.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.local_source import IngestError, ingest_file, ingest_url
from core.state import StateStore

logger = logging.getLogger(__name__)


class DropZone(QFrame):
    """Visible drop target with a URL line-edit."""

    ingested = pyqtSignal(str)  # guid

    def __init__(
        self,
        *,
        state: StateStore,
        watchlist_path: Path,
        max_duration_hours: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._wl_path = watchlist_path
        self._max_hours = max_duration_hours
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        root = QVBoxLayout(self)
        title = QLabel("Drop an audio or video file here — or paste a URL")
        title.setStyleSheet("font-weight: 600;")
        root.addWidget(title)

        hint = QLabel(
            "Supports .mp3 / .m4a / .wav / .mp4 / .mov / .mkv / .webm / … "
            "and any URL yt-dlp recognises."
        )
        hint.setStyleSheet("color: palette(mid);")
        root.addWidget(hint)

        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        url_row.addWidget(self._url_edit, 1)
        go = QPushButton("Ingest URL")
        go.clicked.connect(self._on_go_clicked)
        url_row.addWidget(go)
        root.addLayout(url_row)

    # ── Qt drop plumbing ────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        md = event.mimeData()
        paths: list[Path] = []
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    paths.append(Path(u.toLocalFile()))
        if paths:
            self.handle_paths(paths)
            event.acceptProposedAction()
            return
        if md.hasText():
            text = md.text().strip()
            if text.startswith(("http://", "https://")):
                self.handle_url(text)
                event.acceptProposedAction()
                return

    # ── entry points for UI glue + tests ────────────────────────────────

    def handle_paths(self, paths: Iterable[Path]) -> None:
        for p in paths:
            try:
                guid = ingest_file(
                    p,
                    show_slug=None,
                    state=self._state,
                    watchlist_path=self._wl_path,
                    source="local-drop",
                    max_duration_hours=self._max_hours,
                )
                self.ingested.emit(guid)
            except IngestError as e:
                QMessageBox.warning(self, "Can't ingest", f"{p.name}: {e}")

    def handle_url(self, url: str) -> None:
        try:
            guid = ingest_url(
                url,
                show_slug=None,
                state=self._state,
                watchlist_path=self._wl_path,
            )
            self.ingested.emit(guid)
            self._url_edit.clear()
        except IngestError as e:
            QMessageBox.warning(self, "Can't ingest URL", str(e))

    def _on_go_clicked(self) -> None:
        text = self._url_edit.text().strip()
        if text:
            self.handle_url(text)
```

Wire it into `ui/main_window.py`. Find the Shows-page composition (grep for `ShowsTab(` inside main_window). Above the `ShowsTab` widget in the layout, insert:

```python
        from ui.drop_zone import DropZone
        self.drop_zone = DropZone(
            state=self.ctx.state,
            watchlist_path=DATA / "watchlist.yaml",  # same constant already used elsewhere
            max_duration_hours=self.settings.local_max_duration_hours,
        )
        shows_layout.addWidget(self.drop_zone)
```

Also install a global drop handler on the main window so drops anywhere dispatch. In the `MainWindow.__init__` body, after `self.setAcceptDrops(True)` (add if absent), add or extend:

```python
    def dragEnterEvent(self, event):  # noqa: N802
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802
        # Delegate to the Shows-page drop zone so behaviour matches.
        self.drop_zone.dropEvent(event)
```

**Step 4: Verify pass.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_drop_zone.py -v`
Expected: PASS.

**Step 5: Commit.**

```bash
git add ui/drop_zone.py ui/main_window.py tests/test_drop_zone.py
git commit -m "feat(ui): drop zone on Shows page + global main-window drop handler"
```

---

## Task 10: `ui/import_folder_dialog.py` + File menu entry

**Files:**
- Create: `ui/import_folder_dialog.py`.
- Modify: `ui/main_window.py` (File menu wiring) or `ui/menu_bar.py` (whichever owns File menu today — grep for `addMenu("&File"` / `"File"`).
- Test: `tests/test_import_folder_dialog.py` (new).

**Step 1: Failing smoke test.**

Create `tests/test_import_folder_dialog.py`:

```python
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_dialog_previews_count(tmp_path: Path):
    import PyQt6.QtWidgets as qtw

    _ = qtw.QApplication.instance() or qtw.QApplication([])
    from ui.import_folder_dialog import ImportFolderDialog

    root = tmp_path / "pile"
    root.mkdir()
    (root / "a.wav").write_bytes(b"x")
    (root / "b.mp4").write_bytes(b"x")
    (root / "notes.txt").write_bytes(b"x")

    d = ImportFolderDialog(parent=None)
    d._folder = root  # test hook
    count = d._count_supported(root, recursive=True)
    assert count == 2
```

**Step 2: Verify fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_import_folder_dialog.py -v`
Expected: FAIL (module missing).

**Step 3: Implement.**

Create `ui/import_folder_dialog.py`:

```python
"""Folder-import dialog for the v1.3 universal-ingest feature.

One-shot scan of a chosen directory; queues every recognised media file
under a synthetic show whose slug is either user-supplied or the folder
basename.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.local_source import _MEDIA_EXTS


class ImportFolderDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import folder")
        self._folder: Path | None = None
        self._build()

    # ── exposed for wiring and tests ────────────────────────────────────

    def chosen_folder(self) -> Path | None:
        return self._folder

    def show_slug(self) -> str | None:
        s = self._slug_edit.text().strip()
        return s or None

    def recursive(self) -> bool:
        return self._recurse.isChecked()

    # ── internals ───────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        self._path_label = QLabel("(no folder chosen)")
        pick = QPushButton("Choose folder…")
        pick.clicked.connect(self._pick)
        row.addWidget(self._path_label, 1)
        row.addWidget(pick)
        root.addLayout(row)

        form = QFormLayout()
        self._slug_edit = QLineEdit()
        self._slug_edit.setPlaceholderText("(defaults to folder name)")
        form.addRow("Show slug:", self._slug_edit)
        self._recurse = QCheckBox("Recurse into subfolders")
        self._recurse.setChecked(True)
        form.addRow(self._recurse)
        root.addLayout(form)

        self._preview = QLabel("")
        self._preview.setStyleSheet("color: palette(mid);")
        root.addWidget(self._preview)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._recurse.stateChanged.connect(self._refresh_preview)

    def _pick(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Choose folder")
        if p:
            self._folder = Path(p)
            self._path_label.setText(str(self._folder))
            self._slug_edit.setPlaceholderText(self._folder.name)
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._folder is None:
            return
        n = self._count_supported(self._folder, recursive=self._recurse.isChecked())
        self._preview.setText(f"Found {n} supported file{'s' if n != 1 else ''}")

    @staticmethod
    def _count_supported(folder: Path, *, recursive: bool) -> int:
        it = folder.rglob("*") if recursive else folder.iterdir()
        return sum(
            1 for p in it if p.is_file() and p.suffix.lower() in _MEDIA_EXTS
        )
```

Wire a `File → Import folder…` entry. Find the file that builds the File menu (grep for `addMenu("&File")` or `file_menu.addAction`). Add an action:

```python
        act_import = file_menu.addAction("Import folder…")
        act_import.triggered.connect(self._on_import_folder)
```

And the slot:

```python
    def _on_import_folder(self) -> None:
        from ui.import_folder_dialog import ImportFolderDialog
        from core.local_source import ingest_folder

        dlg = ImportFolderDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        folder = dlg.chosen_folder()
        if folder is None:
            return
        guids = ingest_folder(
            folder,
            show_slug=dlg.show_slug(),
            state=self.ctx.state,
            watchlist_path=DATA / "watchlist.yaml",
            recursive=dlg.recursive(),
            max_duration_hours=self.settings.local_max_duration_hours,
        )
        self.statusBar().showMessage(
            f"Imported {len(guids)} file{'s' if len(guids) != 1 else ''}", 5000
        )
```

**Step 4: Verify pass.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_import_folder_dialog.py -v`
Expected: PASS.

**Step 5: Commit.**

```bash
git add ui/import_folder_dialog.py ui/main_window.py tests/test_import_folder_dialog.py
git commit -m "feat(ui): Import folder dialog + File menu entry"
```

(Adjust staged paths if the File-menu wiring actually lives in `ui/menu_bar.py`.)

---

## Task 11: CLI `ingest` subcommands

Adds `paragraphos ingest file|url|folder`. Each returns newline-separated GUIDs for agent chaining.

**Files:**
- Modify: `cli.py`.
- Test: `tests/test_cli_ingest.py` (new).

**Step 1: Failing test.**

Create `tests/test_cli_ingest.py`:

```python
"""CLI smoke for `paragraphos ingest …`."""

import subprocess
from pathlib import Path


def test_ingest_file_cli_returns_guid(tmp_path: Path, monkeypatch):
    # Point paragraphos at a fresh data dir so we don't clobber the real
    # watchlist / state.
    support = tmp_path / "support"
    support.mkdir()
    monkeypatch.setenv("PARAGRAPHOS_DATA_DIR", str(support))

    (tmp_path / "a.wav").write_bytes(b"x")
    src = tmp_path / "a.wav"

    # Stub ffprobe by injecting a fake on the PATH? Easier: call the
    # command function directly.
    from core.state import StateStore
    from core.models import Watchlist
    state = StateStore(support / "state.sqlite"); state.init_schema()
    Watchlist().save(support / "watchlist.yaml")

    import cli
    monkeypatch.setattr("core.local_source.has_audio_stream", lambda p: True)
    monkeypatch.setattr("core.local_source.duration_seconds", lambda p: 10)

    import argparse
    args = argparse.Namespace(path=str(src), show=None, json=False)
    rc = cli.cmd_ingest_file(args)
    assert rc == 0
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_cli_ingest.py -v`
Expected: FAIL (`cmd_ingest_file` missing).

**Step 3: Implement.**

Edit `cli.py`. Near the other `cmd_*` definitions (e.g. after `cmd_retry_feed`), add:

```python
def cmd_ingest_file(args: argparse.Namespace) -> int:
    from core.local_source import IngestError, ingest_file

    state = _state()
    try:
        guid = ingest_file(
            Path(args.path),
            show_slug=args.show,
            state=state,
            watchlist_path=DATA / "watchlist.yaml",
            source="local-drop",
            max_duration_hours=_settings().local_max_duration_hours,
        )
    except IngestError as e:
        print(f"ingest failed: {e}", file=sys.stderr)
        return 2
    print(guid)
    return 0


def cmd_ingest_url(args: argparse.Namespace) -> int:
    from core.local_source import IngestError, ingest_url

    try:
        guid = ingest_url(
            args.url,
            show_slug=args.show,
            state=_state(),
            watchlist_path=DATA / "watchlist.yaml",
        )
    except IngestError as e:
        print(f"ingest failed: {e}", file=sys.stderr)
        return 2
    print(guid)
    return 0


def cmd_ingest_folder(args: argparse.Namespace) -> int:
    from core.local_source import ingest_folder

    guids = ingest_folder(
        Path(args.path),
        show_slug=args.show,
        state=_state(),
        watchlist_path=DATA / "watchlist.yaml",
        recursive=args.recursive,
        max_duration_hours=_settings().local_max_duration_hours,
    )
    for g in guids:
        print(g)
    return 0
```

Also register the parsers. Inside `main()`, before `args = p.parse_args()`:

```python
    s_ing = sub.add_parser("ingest", help="one-off ingest of a file / URL / folder")
    ing_sub = s_ing.add_subparsers(dest="ingest_what", required=True)

    s_if = ing_sub.add_parser("file", help="ingest one local media file")
    s_if.add_argument("path")
    s_if.add_argument("--show", default=None)
    s_if.set_defaults(fn=cmd_ingest_file)

    s_iu = ing_sub.add_parser("url", help="ingest a URL via yt-dlp generic extractor")
    s_iu.add_argument("url")
    s_iu.add_argument("--show", default=None)
    s_iu.set_defaults(fn=cmd_ingest_url)

    s_ifo = ing_sub.add_parser("folder", help="ingest every supported file in a folder")
    s_ifo.add_argument("path")
    s_ifo.add_argument("--show", default=None)
    s_ifo.add_argument("--recursive", action="store_true", default=True)
    s_ifo.add_argument(
        "--no-recursive", dest="recursive", action="store_false",
        help="only scan the top-level directory",
    )
    s_ifo.set_defaults(fn=cmd_ingest_folder)
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_cli_ingest.py -v`
Expected: PASS.

**Step 5: Full suite.**

Run: `.venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit.**

```bash
git add cli.py tests/test_cli_ingest.py
git commit -m "feat(cli): ingest file | url | folder subcommands"
```

---

## Task 12: CLI `watch` subcommands

List / add / remove watch-folder paths. For v1.3 we keep a single root (Settings.watch_folder_root) — `add` sets it, `remove` disables the watcher. Multi-root support is a follow-up.

**Files:**
- Modify: `cli.py`.
- Test: `tests/test_cli_watch.py` (new).

**Step 1: Failing test.**

Create `tests/test_cli_watch.py`:

```python
"""CLI smoke for `paragraphos watch …`."""

from pathlib import Path


def test_watch_add_enables_and_sets_root(tmp_path: Path, monkeypatch):
    support = tmp_path / "support"
    support.mkdir()
    monkeypatch.setenv("PARAGRAPHOS_DATA_DIR", str(support))

    root = tmp_path / "z"; root.mkdir()

    from core.models import Settings
    Settings().save(support / "settings.yaml")

    import argparse
    import cli
    rc = cli.cmd_watch_add(argparse.Namespace(path=str(root)))
    assert rc == 0
    s = Settings.load(support / "settings.yaml")
    assert s.watch_folder_enabled is True
    assert Path(s.watch_folder_root).expanduser() == root


def test_watch_remove_disables(tmp_path: Path, monkeypatch):
    support = tmp_path / "support"
    support.mkdir()
    monkeypatch.setenv("PARAGRAPHOS_DATA_DIR", str(support))

    from core.models import Settings
    s = Settings(watch_folder_enabled=True, watch_folder_root=str(tmp_path / "z"))
    s.save(support / "settings.yaml")

    import argparse
    import cli
    rc = cli.cmd_watch_remove(argparse.Namespace())
    assert rc == 0
    assert Settings.load(support / "settings.yaml").watch_folder_enabled is False
```

Note: `PARAGRAPHOS_DATA_DIR` is not a current env var. If honouring one requires changes to `core/paths.py`, do it here as part of this task (a small, backwards-compatible override that `user_data_dir()` consults before the macOS-conventional path). Otherwise swap the tests to point at the default support dir via monkey-patching `core.paths.user_data_dir` (same pattern as existing CLI tests).

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_cli_watch.py -v`
Expected: FAIL.

**Step 3: Implement.**

Edit `cli.py`. Add:

```python
def cmd_watch_add(args: argparse.Namespace) -> int:
    s = _settings()
    s.watch_folder_enabled = True
    s.watch_folder_root = str(Path(args.path).expanduser().resolve())
    s.save(DATA / "settings.yaml")
    print(f"watch folder: {s.watch_folder_root} (enabled)")
    return 0


def cmd_watch_remove(_args: argparse.Namespace) -> int:
    s = _settings()
    s.watch_folder_enabled = False
    s.save(DATA / "settings.yaml")
    print("watch folder disabled")
    return 0


def cmd_watch_list(args: argparse.Namespace) -> int:
    s = _settings()
    payload = {
        "enabled": s.watch_folder_enabled,
        "root": str(Path(s.watch_folder_root).expanduser()),
        "post": s.watch_folder_post,
        "max_duration_hours": s.local_max_duration_hours,
    }
    _emit(
        payload,
        as_json=getattr(args, "json", False),
        human=f"{'on' if payload['enabled'] else 'off':3} {payload['root']}",
    )
    return 0
```

Register parsers near the ingest block:

```python
    s_w = sub.add_parser("watch", help="manage the watch-folder source")
    w_sub = s_w.add_subparsers(dest="watch_cmd", required=True)

    s_wa = w_sub.add_parser("add", help="enable watching + set the root path")
    s_wa.add_argument("path")
    s_wa.set_defaults(fn=cmd_watch_add)

    w_sub.add_parser("remove", help="disable the watcher").set_defaults(fn=cmd_watch_remove)

    s_wl = w_sub.add_parser("list", help="show watch-folder config")
    s_wl.add_argument("--json", action="store_true")
    s_wl.set_defaults(fn=cmd_watch_list)
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_cli_watch.py -v`
Expected: PASS.

**Step 5: Commit.**

```bash
git add cli.py tests/test_cli_watch.py
git commit -m "feat(cli): watch add | remove | list subcommands"
```

---

## Task 13: Wire `WatchFolder` into `app.py` startup

The watch-folder observer is created and started when the app launches (subject to `Settings.watch_folder_enabled`), and stopped on shutdown.

**Files:**
- Modify: `app.py`.
- Test: `tests/test_app_watch_folder_wiring.py` (new — light smoke).

**Step 1: Failing test.**

Create `tests/test_app_watch_folder_wiring.py`:

```python
"""App-level wiring: WatchFolder starts iff Settings.watch_folder_enabled."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_watch_folder_not_started_when_disabled(tmp_path, monkeypatch):
    from core.models import Settings

    s = Settings(watch_folder_enabled=False)

    # Import the factory/helper. If app.py names it differently, adjust
    # the import; the public contract is: returns a started WatchFolder
    # or None.
    from app import maybe_start_watch_folder

    wf = maybe_start_watch_folder(
        settings=s, state=None, watchlist_path=tmp_path / "wl.yaml"
    )
    assert wf is None


def test_watch_folder_starts_when_enabled(tmp_path, monkeypatch):
    from core.models import Settings
    from core.state import StateStore

    root = tmp_path / "z"; root.mkdir()
    s = Settings(watch_folder_enabled=True, watch_folder_root=str(root))

    state = StateStore(tmp_path / "s.sqlite"); state.init_schema()
    (tmp_path / "wl.yaml").write_text("shows: []\n", encoding="utf-8")

    from app import maybe_start_watch_folder

    wf = maybe_start_watch_folder(
        settings=s, state=state, watchlist_path=tmp_path / "wl.yaml"
    )
    assert wf is not None
    wf.stop()
```

**Step 2: Verify fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_watch_folder_wiring.py -v`
Expected: FAIL — `maybe_start_watch_folder` missing.

**Step 3: Implement.**

Add to `app.py` (top-level, near other helpers):

```python
def maybe_start_watch_folder(
    *,
    settings,
    state,
    watchlist_path,
):
    """Create + start a WatchFolder iff enabled in settings. Returns the
    instance (or None). Callers own the stop()."""
    from core.watch_folder import WatchFolder

    if not getattr(settings, "watch_folder_enabled", False):
        return None
    wf = WatchFolder(
        root=Path(settings.watch_folder_root).expanduser(),
        state=state,
        watchlist_path=watchlist_path,
        max_duration_hours=settings.local_max_duration_hours,
    )
    wf.start()
    return wf
```

In the existing startup sequence (find where other long-lived observers — `LibraryIndex.start_watching`, `ConnectivityMonitor`, `BackgroundScheduler` — are wired), add:

```python
    watch_folder = maybe_start_watch_folder(
        settings=settings, state=state, watchlist_path=DATA / "watchlist.yaml"
    )
```

And in the shutdown/aboutToQuit handler:

```python
    if watch_folder is not None:
        watch_folder.stop()
```

**Step 4: Verify pass.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_app_watch_folder_wiring.py -v`
Expected: PASS.

**Step 5: Full suite.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit.**

```bash
git add app.py tests/test_app_watch_folder_wiring.py
git commit -m "feat(app): start WatchFolder observer when enabled in settings"
```

---

## Task 14: Docs + CHANGELOG + version bump

**Files:**
- Modify: `CHANGELOG.md`.
- Modify: `README.md` (new subsection under "What it does").
- Modify: `core/version.py`.

**Step 1: Bump version.**

Edit `core/version.py` — set `VERSION = "1.3.0"`.

**Step 2: CHANGELOG.**

Prepend to `CHANGELOG.md`:

```markdown
## v1.3.0 — 2026-04-23 (universal ingest)

### Added
- **Universal ingest.** Beyond RSS podcasts and YouTube channels,
  Paragraphos now accepts any audio or video file — dropped on the
  Shows page, dropped anywhere on the main window, pasted as a URL,
  picked up from a watched folder, or batch-imported from an existing
  directory.
- **Drop zone** on the Shows page with a URL line-edit. Files
  land with default show `files`; URLs dispatch through yt-dlp's
  generic extractor (~1000 supported sites) and use the uploader as
  the show slug when known, `web` otherwise.
- **Watch folder** (Settings → Local sources). New files landing in
  top-level subfolders auto-queue against a show derived from the
  subfolder name. `~/Paragraphos/to-be-transcribed/zoom/*.mp4` → show
  `zoom`.
- **Folder import** (File → Import folder…). One-shot scan + queue of
  every supported file in a chosen directory tree.
- **CLI parity:** `paragraphos ingest file | url | folder`,
  `paragraphos watch add | remove | list`.

### Internal
- New modules: `core/local_source.py`, `core/watch_folder.py`,
  `ui/drop_zone.py`, `ui/import_folder_dialog.py`.
- `core/pipeline.process_episode` gains a `local` source branch that
  bypasses `download_mp3` (source files are copied into staging).
- `Show.source` adds `local-folder | local-drop | url` values alongside
  `podcast | youtube`.
- `Settings` gains `watch_folder_enabled / watch_folder_root /
  watch_folder_post / local_max_duration_hours`.
```

**Step 3: README.**

Under the "What it does" bullet list in `README.md`, add:

```markdown
- 📥 **Ingests any file or URL** — drop an `.mp4` / `.wav` / `.m4a` /
  `.mov` onto the window, or paste a URL (SoundCloud, Vimeo, any site
  yt-dlp recognises). A watched folder at
  `~/Paragraphos/to-be-transcribed/` auto-queues new drops.
```

**Step 4: Verify suites still green.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: green.

**Step 5: Commit.**

```bash
git add core/version.py CHANGELOG.md README.md
git commit -m "chore(release): v1.3.0 — universal ingest"
```

---

## Verification before calling the release done

Run each and confirm:

1. `.venv/bin/python -m pytest -q` — all green.
2. Drop an `.mp4` onto the running app → appears in Queue as pending → completes. Check output folder has `.md`.
3. Paste a YouTube URL into the drop-zone line-edit → queue grows → completes.
4. Enable watch folder in Settings → drop a `.wav` into the subfolder → queue grows within ~5 s.
5. File → Import folder → pick a dir with 3 media files + noise → "Found 3 supported files" → Import → 3 pendings queued.
6. `.venv/bin/python cli.py ingest file <path-to-wav>` prints a `sha256:…` GUID and the file shows up in the Queue.
7. `.venv/bin/python cli.py watch add ~/some/folder; cli.py watch list` — enabled/root printed.
8. Drop a video-with-no-audio `.mp4` → lands in Failed tab with "no audio stream" reason.
9. Pull the USB-drive hosting the watch folder → banner / paused state; re-plug → resume.
10. Manual Obsidian open of the generated `.md` renders clean.

Only after all ten are checked do we tag v1.3.0.

---

## Out of scope (deferred)

- Full-text search across transcripts (belongs to the downstream LLM/wiki layer).
- Speaker diarization, semantic embeddings, chapter segmentation.
- Multi-root watch folders (v1.3 is single-root; a later minor can loop).
- Code signing / notarisation.
- Web UI / headless daemon.
