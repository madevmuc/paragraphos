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
