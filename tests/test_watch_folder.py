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

    monkeypatch.setattr(local_source, "probe_audio_state", lambda p: "audio")
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
                row = c.execute("SELECT * FROM episodes WHERE show_slug='zoom' LIMIT 1").fetchone()
            if row:
                ep = dict(row)
                break
            time.sleep(0.05)
        assert ep is not None
        assert ep["status"] == "pending"
    finally:
        wf.stop()


def test_watch_folder_handles_on_moved_event(tmp_path: Path, monkeypatch):
    """Atomic-rename writes (Zoom Cloud, .crdownload → final, mv across
    filesystems) fire on_moved, not on_created. Confirm we pick them up."""
    from core import local_source, watch_folder

    root = tmp_path / "watch"
    root.mkdir()
    (root / "zoom").mkdir()

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    monkeypatch.setattr(local_source, "probe_audio_state", lambda p: "audio")
    monkeypatch.setattr(local_source, "has_audio_stream", lambda p: True)
    monkeypatch.setattr(local_source, "duration_seconds", lambda p: 60)

    wf = watch_folder.WatchFolder(
        root=root, state=state, watchlist_path=wl_path, debounce_seconds=0.0
    )
    wf.start()
    try:
        # Simulate an atomic rename: write under the watched root but
        # outside `zoom/`, then rename into `zoom/`. The rename fires
        # on_moved inside the Observer.
        staging = root / ".staging.mp4"
        staging.write_bytes(b"x")
        final = root / "zoom" / "standup.mp4"
        staging.rename(final)

        import time

        deadline = time.time() + 3.0
        ep = None
        while time.time() < deadline:
            with state._conn() as c:
                row = c.execute("SELECT * FROM episodes WHERE show_slug='zoom' LIMIT 1").fetchone()
            if row:
                ep = dict(row)
                break
            time.sleep(0.05)
        assert ep is not None, "on_moved event did not result in an ingested episode"
        assert ep["status"] == "pending"
    finally:
        wf.stop()


def test_watch_folder_does_not_retry_on_clean_no_audio(tmp_path: Path, monkeypatch):
    """A cleanly-probed silent file (e.g. timelapse) should skip without
    paying the 5 s retry cost. Only ffprobe *errors* warrant a retry."""
    from core import local_source, watch_folder

    root = tmp_path / "watch"
    root.mkdir()

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    # If the retry path fires, call #2 would return "audio" and we'd
    # see an episode row. A pass means the retry was correctly skipped.
    calls = {"n": 0}

    def counting_probe(_p):
        calls["n"] += 1
        if calls["n"] == 1:
            return "no_audio"
        return "audio"

    monkeypatch.setattr(local_source, "probe_audio_state", counting_probe)
    monkeypatch.setattr(local_source, "duration_seconds", lambda p: 60)

    wf = watch_folder.WatchFolder(
        root=root, state=state, watchlist_path=wl_path, debounce_seconds=0.0
    )
    # Call _handle_new_file directly — avoids watchdog Observer nondeterminism.
    # No need for wf.start(); the handler method doesn't require it.
    f = root / "silent.mp4"
    f.write_bytes(b"x")
    wf._handle_new_file(f)

    assert calls["n"] == 1, f"expected 1 probe call, got {calls['n']} — retry fired"

    # And no episode should have been written.
    with state._conn() as c:
        row = c.execute("SELECT * FROM episodes LIMIT 1").fetchone()
    assert row is None


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


def test_watch_folder_resumes_when_root_appears(tmp_path: Path):
    """After start() paused itself on a missing root, check_for_resume()
    should re-start the observer once the root exists."""
    from core.watch_folder import WatchFolder

    root = tmp_path / "not-yet"
    # NOT created — start() will pause.

    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    wf = WatchFolder(root=root, state=state, watchlist_path=wl_path, debounce_seconds=0.0)
    wf.start()
    assert wf.is_paused()

    # check_for_resume is a no-op while the root is still missing.
    wf.check_for_resume()
    assert wf.is_paused()

    # Create the root; re-check should flip paused off and start observer.
    root.mkdir()
    wf.check_for_resume()
    try:
        assert not wf.is_paused()
        # Observer is running (attribute set).
        assert wf._observer is not None
    finally:
        wf.stop()


def test_watch_folder_check_for_resume_is_noop_when_already_running(tmp_path: Path):
    """Calling check_for_resume on a healthy (non-paused) watcher must
    not recreate the Observer (which would leak a thread)."""
    from core.watch_folder import WatchFolder

    root = tmp_path / "live"
    root.mkdir()
    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    wf = WatchFolder(root=root, state=state, watchlist_path=wl_path, debounce_seconds=0.0)
    wf.start()
    try:
        assert not wf.is_paused()
        obs_before = wf._observer
        wf.check_for_resume()
        assert wf._observer is obs_before  # same instance, not re-started
    finally:
        wf.stop()
