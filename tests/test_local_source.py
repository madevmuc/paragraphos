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


def test_probe_audio_state_distinguishes_no_audio_from_error(monkeypatch):
    from core import local_source

    # Case 1: returncode=0 + audio stream present → "audio"
    def fake_audio(args, **kw):
        class R:
            returncode = 0
            stdout = '{"streams":[{"codec_type":"audio","codec_name":"aac"}]}'
            stderr = ""

        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_audio)
    assert local_source.probe_audio_state(Path("/nonexistent.mp4")) == "audio"

    # Case 2: returncode=0 + only a video stream → "no_audio"
    def fake_video_only(args, **kw):
        class R:
            returncode = 0
            stdout = '{"streams":[{"codec_type":"video","codec_name":"h264"}]}'
            stderr = ""

        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_video_only)
    assert local_source.probe_audio_state(Path("/nonexistent.mp4")) == "no_audio"

    # Case 3: returncode=1 (ffprobe error) → "error"
    def fake_error(args, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = "Invalid data found"

        return R()

    monkeypatch.setattr(local_source.subprocess, "run", fake_error)
    assert local_source.probe_audio_state(Path("/nonexistent.mp4")) == "error"


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

    guids = ingest_folder(root, show_slug=None, state=state, watchlist_path=wl_path, recursive=True)
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

    guid = ingest_url(
        "https://vimeo.com/12345", show_slug=None, state=state, watchlist_path=wl_path
    )
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
