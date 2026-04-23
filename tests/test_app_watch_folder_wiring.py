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

    wf = maybe_start_watch_folder(settings=s, state=None, watchlist_path=tmp_path / "wl.yaml")
    assert wf is None


def test_watch_folder_starts_when_enabled(tmp_path, monkeypatch):
    from core.models import Settings
    from core.state import StateStore

    root = tmp_path / "z"
    root.mkdir()
    s = Settings(watch_folder_enabled=True, watch_folder_root=str(root))

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    (tmp_path / "wl.yaml").write_text("shows: []\n", encoding="utf-8")

    from app import maybe_start_watch_folder

    wf = maybe_start_watch_folder(settings=s, state=state, watchlist_path=tmp_path / "wl.yaml")
    assert wf is not None
    wf.stop()
