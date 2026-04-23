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
                row = c.execute("SELECT * FROM episodes WHERE show_slug='zoom' LIMIT 1").fetchone()
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
