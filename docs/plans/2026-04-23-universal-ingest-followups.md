# Universal Ingest — Follow-ups Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the three Important items flagged during v1.3.0 universal-ingest code review — valid `file://` URIs for non-ASCII paths, non-blocking UI for drop-zone ingest/URL-probe, and auto-resume when the watched root re-mounts.

**Architecture:** Three small, independent fixes. Task 1 is a one-line swap (`f"file://{p}"` → `Path(p).as_uri()`). Task 2 introduces a `QRunnable` worker in `ui/drop_zone.py` so large-file hashing and `yt-dlp` probes leave the main thread (mirrors `ui/feed_probe.py`). Task 3 adds a `QTimer`-backed re-check inside `WatchFolder` so an unmounted-then-replugged external drive doesn't require an app restart.

**Tech Stack:** Python 3.12, PyQt6 6.7 (`QThreadPool` / `QRunnable` / `pyqtSignal` / `QTimer`), pytest + `QT_QPA_PLATFORM=offscreen` for UI smokes.

**Design source:** code-review findings on v1.3.0 (see commits `af3fa5a` Task 5, `59f0872` Task 9, `2b0fe6b` Task 7).

**Working branch:** continue on `ship-v1` (linear history; cut `v1.3.1` once all three tasks land).

**Related skills:**
- @superpowers:test-driven-development
- @superpowers:verification-before-completion

---

## Conventions for this plan

- Every step runs from `~/dev/paragraphos/`.
- Python is invoked as `.venv/bin/python`.
- Tests: `.venv/bin/python -m pytest tests/<file> -v` targeted; `.venv/bin/python -m pytest -q` full.
- UI-smoke tests need `QT_QPA_PLATFORM=offscreen` prepended.
- Each numbered Task ends with one commit. Conventional Commits (`fix(scope): …`, `feat(scope): …`, `test(scope): …`).
- Never skip pre-commit with `--no-verify`. If ruff reformats on commit, re-stage and make a new commit (no `--amend`).

---

## Task 1: `Path.as_uri()` for `mp3_url` on local-file ingest

`core/local_source.ingest_file` stores `mp3_url=f"file://{p}"` at line 324. `Path("/Users/me/Zoom Meetings/intro.mp4")` becomes the invalid URI `file:///Users/me/Zoom Meetings/intro.mp4` (raw space; fails `urllib.parse`). `Path(p).as_uri()` produces the RFC 3986 form `file:///Users/me/Zoom%20Meetings/intro.mp4`. The pipeline reads `state.meta["local_path:<guid>"]` for the real path (so cosmetic today), but the `mp3_url` field is surfaced in CLI `paragraphos episodes <slug> --json` output and may round-trip via parsers in future work — keep it valid.

**Files:**
- Modify: `core/local_source.py:324`
- Test: `tests/test_local_source.py` (extend)

**Step 1: Write the failing test**

Append to `tests/test_local_source.py`:

```python
def test_ingest_file_url_encodes_spaces_and_non_ascii(tmp_path: Path):
    from core import local_source
    from core.local_source import ingest_file

    # Filename with a space AND a non-ASCII character (German umlaut).
    d = tmp_path / "Zoom Meetings"
    d.mkdir()
    f = d / "Büro 2026.wav"
    f.write_bytes(b"hello")
    state = _fresh_state(tmp_path)
    wl_path = _seed_watchlist(tmp_path)

    local_source.has_audio_stream = lambda p: True  # type: ignore[assignment]
    local_source.duration_seconds = lambda p: 42  # type: ignore[assignment]

    guid = ingest_file(f, show_slug=None, state=state, watchlist_path=wl_path)

    ep = state.get_episode(guid)
    assert ep is not None
    url = ep["mp3_url"]
    # Must be a valid file URI — no raw spaces, non-ASCII percent-encoded.
    assert " " not in url
    assert url.startswith("file:///")
    # Percent-encoded forms (uppercase hex per RFC 3986 §2.1).
    assert "Zoom%20Meetings" in url
    assert "B%C3%BCro%202026" in url  # Büro → B%C3%BCro, space → %20
    # urllib round-trips cleanly.
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url)
    assert parsed.scheme == "file"
    assert unquote(parsed.path).endswith("Büro 2026.wav")
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_local_source.py::test_ingest_file_url_encodes_spaces_and_non_ascii -v`
Expected: FAIL — `mp3_url` contains raw space; `"Zoom%20Meetings"` not found.

**Step 3: Write minimal implementation**

Edit `core/local_source.py` line 324. Replace:

```python
        mp3_url=f"file://{p}",
```

with:

```python
        mp3_url=p.as_uri(),
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_local_source.py -v`
Expected: all PASS (new test + existing 19+ tests).

**Step 5: Full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit**

```bash
git add core/local_source.py tests/test_local_source.py
git commit -m "fix(local-source): percent-encode mp3_url via Path.as_uri()"
```

---

## Task 2: Off-main-thread `DropZone` ingest

`DropZone.handle_paths` and `handle_url` in `ui/drop_zone.py` run synchronously on the UI thread. A 1 GB drop spends seconds SHA-256-hashing; a pasted URL spends up to 60 s in `_yt_dlp_probe`'s subprocess. Both freeze the window — the OS paints the "not responding" spinner well before they return.

Solution: hoist both entry points onto `QThreadPool.globalInstance()` via a `QRunnable` mirroring `ui/feed_probe.FeedProbeWorker`. Result (guid or error) is emitted back on the main thread via a `pyqtSignal` and the existing `ingested` signal + `QMessageBox.warning` plumbing runs in a main-thread slot.

**Files:**
- Modify: `ui/drop_zone.py` (refactor `handle_paths`, `handle_url`; add `_IngestRunnable` class)
- Test: `tests/test_drop_zone.py` (extend — assert the runnable is submitted, assert the result is emitted on `ingested`)

**Step 1: Write the failing test**

Append to `tests/test_drop_zone.py`:

```python
def test_drop_zone_runs_ingest_off_main_thread(tmp_path: Path, monkeypatch):
    """handle_paths must submit a QRunnable to QThreadPool rather than
    calling ingest_file inline on the UI thread."""
    import PyQt6.QtWidgets as qtw
    from PyQt6.QtCore import QThreadPool

    _ = qtw.QApplication.instance() or qtw.QApplication([])

    from core.state import StateStore
    from ui.drop_zone import DropZone

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    (tmp_path / "watchlist.yaml").write_text("shows: []\n", encoding="utf-8")

    # Count how often ingest_file is called AND on which thread.
    import threading

    called = {"main_thread_id": threading.get_ident(), "calls": []}

    def fake_ingest_file(path, **kw):
        called["calls"].append({"tid": threading.get_ident(), "path": path})
        return "sha256:fake"

    monkeypatch.setattr("ui.drop_zone.ingest_file", fake_ingest_file)

    dz = DropZone(
        state=state,
        watchlist_path=tmp_path / "watchlist.yaml",
        max_duration_hours=4,
    )

    guids: list[str] = []
    dz.ingested.connect(guids.append)

    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    dz.handle_paths([f])

    # Wait for the pool to drain (up to 3 s).
    QThreadPool.globalInstance().waitForDone(3000)
    # Pump the event loop so the cross-thread signal delivers.
    for _ in range(20):
        qtw.QApplication.processEvents()

    assert len(called["calls"]) == 1
    assert called["calls"][0]["path"] == f
    # Must NOT have been called on the main thread.
    assert called["calls"][0]["tid"] != called["main_thread_id"]
    # The signal fired on the main thread with the guid.
    assert guids == ["sha256:fake"]


def test_drop_zone_runs_url_ingest_off_main_thread(tmp_path: Path, monkeypatch):
    import PyQt6.QtWidgets as qtw
    from PyQt6.QtCore import QThreadPool

    _ = qtw.QApplication.instance() or qtw.QApplication([])

    from core.state import StateStore
    from ui.drop_zone import DropZone

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    (tmp_path / "watchlist.yaml").write_text("shows: []\n", encoding="utf-8")

    import threading

    main_tid = threading.get_ident()
    calls: list[dict] = []

    def fake_ingest_url(url, **kw):
        calls.append({"tid": threading.get_ident(), "url": url})
        return "Vimeo:fake"

    monkeypatch.setattr("ui.drop_zone.ingest_url", fake_ingest_url)

    dz = DropZone(
        state=state,
        watchlist_path=tmp_path / "watchlist.yaml",
        max_duration_hours=4,
    )
    guids: list[str] = []
    dz.ingested.connect(guids.append)

    dz.handle_url("https://vimeo.com/42")

    QThreadPool.globalInstance().waitForDone(3000)
    for _ in range(20):
        qtw.QApplication.processEvents()

    assert len(calls) == 1
    assert calls[0]["url"] == "https://vimeo.com/42"
    assert calls[0]["tid"] != main_tid
    assert guids == ["Vimeo:fake"]
```

Delete the two existing tests `test_drop_zone_accepts_file_uri` and `test_drop_zone_accepts_url_text` — they assert inline-synchronous behavior that this task is intentionally breaking. The two new tests cover the same paths (that `ingest_file`/`ingest_url` eventually see the right args) plus the threading invariant.

**Step 2: Run test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_drop_zone.py -v`
Expected: FAIL — the new tests fail because `ingest_file` currently runs on the main thread (`called["tid"] == main_thread_id`).

**Step 3: Write minimal implementation**

Rewrite `ui/drop_zone.py`. Keep the existing ctor and Qt-drop plumbing; replace the two synchronous methods and add the runnable + signal glue:

```python
"""Drop-target widget for the v1.3 universal-ingest feature.

A card on the Shows page shows the prompt and hosts the URL input. It
doubles as a dispatcher for the main window's global ``dropEvent`` so
a user can drag a file anywhere and it still works.

Ingest work (SHA-256 hashing, yt-dlp probe) is dispatched to
``QThreadPool.globalInstance()`` so the UI stays responsive even for
large files or slow URL probes. Mirrors the ``QRunnable`` pattern used
by ``ui.feed_probe``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
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


class _IngestSignals(QObject):
    # (guid, None) on success; (None, error_detail) on failure.
    done = pyqtSignal(object, object)


class _IngestRunnable(QRunnable):
    """Runs ``ingest_file`` or ``ingest_url`` off the main thread."""

    def __init__(self, kind: str, payload, **kw) -> None:
        super().__init__()
        self._kind = kind  # "file" | "url"
        self._payload = payload
        self._kw = kw
        self._signals = _IngestSignals()
        self.done = self._signals.done

    def run(self) -> None:
        try:
            if self._kind == "file":
                guid = ingest_file(self._payload, **self._kw)
            else:
                guid = ingest_url(self._payload, **self._kw)
        except IngestError as e:
            self._signals.done.emit(None, str(e))
            return
        except Exception as e:  # pragma: no cover — defensive
            logger.exception("drop-zone ingest crashed")
            self._signals.done.emit(None, f"unexpected error: {e}")
            return
        self._signals.done.emit(guid, None)


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
        self._go_btn = QPushButton("Ingest URL")
        self._go_btn.clicked.connect(self._on_go_clicked)
        url_row.addWidget(self._go_btn)
        root.addLayout(url_row)

        # Keep a reference to in-flight runnables so Qt doesn't GC their
        # signals before the emit lands on the main thread.
        self._pending: list[_IngestRunnable] = []

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
            self._submit(
                _IngestRunnable(
                    "file",
                    p,
                    show_slug=None,
                    state=self._state,
                    watchlist_path=self._wl_path,
                    source="local-drop",
                    max_duration_hours=self._max_hours,
                ),
                label=p.name,
            )

    def handle_url(self, url: str) -> None:
        self._go_btn.setEnabled(False)
        r = _IngestRunnable(
            "url",
            url,
            show_slug=None,
            state=self._state,
            watchlist_path=self._wl_path,
        )
        # Re-enable the button + clear the line-edit on success.
        def _after(guid, err, _url=url):
            self._go_btn.setEnabled(True)
            if err is None:
                self._url_edit.clear()
        r.done.connect(_after)
        self._submit(r, label=url)

    # ── internals ───────────────────────────────────────────────────────

    def _submit(self, runnable: _IngestRunnable, *, label: str) -> None:
        self._pending.append(runnable)

        def _handle(guid, err, _label=label, _r=runnable):
            try:
                self._pending.remove(_r)
            except ValueError:
                pass
            if err is not None:
                QMessageBox.warning(self, "Can't ingest", f"{_label}: {err}")
                return
            self.ingested.emit(guid)

        runnable.done.connect(_handle)
        QThreadPool.globalInstance().start(runnable)

    def _on_go_clicked(self) -> None:
        text = self._url_edit.text().strip()
        if text:
            self.handle_url(text)
```

**Step 4: Run test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_drop_zone.py -v`
Expected: both new tests PASS (ingest called on a worker thread; `ingested` signal fires on main thread with the GUID).

**Step 5: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: green. (The old test names are deleted; the full count drops by 2 and rises by 2.)

**Step 6: Commit**

```bash
git add ui/drop_zone.py tests/test_drop_zone.py
git commit -m "feat(drop-zone): hoist ingest + URL probe onto QThreadPool worker"
```

---

## Task 3: Watch-root auto-resume on re-mount

`WatchFolder.start()` at `core/watch_folder.py:73-76` pauses itself when the root doesn't exist (unmounted drive, path renamed, etc.). Today the only recovery is quitting + relaunching the app — a miss for users who unplug and re-plug their `~/Paragraphos/to-be-transcribed` on an external SSD. The plan's design doc (`2026-04-23-universal-ingest-design.md` §3) explicitly promised "auto-resume on re-mount."

Solution: a `QTimer`-polled re-check. When paused, tick every `recheck_seconds` (default 30 s). On a tick, if the root now exists, call `start()` again; the observer re-schedules and `_paused` flips to False. No threading — the timer runs on the main thread (`QTimer`'s default) and only calls `start()` which is quick.

Why a timer and not a watcher-on-the-parent-dir? Parent-dir watchers fail silently when the parent itself is unmounted (e.g. `/Volumes` is stable but `/Volumes/ExtSSD` disappears when ejected). A 30 s poll is boring, cheap, and correct across every mount/unmount pattern.

**Files:**
- Modify: `core/watch_folder.py` (add `recheck_seconds` kwarg, add `check_for_resume()` method)
- Modify: `app.py` (wire the timer alongside the existing `maybe_start_watch_folder` call)
- Test: `tests/test_watch_folder.py` (extend)

**Step 1: Write the failing test**

Append to `tests/test_watch_folder.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_watch_folder.py -v`
Expected: FAIL — `AttributeError: 'WatchFolder' object has no attribute 'check_for_resume'`.

**Step 3: Write minimal implementation**

Edit `core/watch_folder.py`. Add the method below `is_paused`:

```python
    def check_for_resume(self) -> None:
        """If paused (root missing), re-run ``start()``. Idempotent —
        does nothing while the observer is already running.

        Intended to be called on a ~30 s ``QTimer`` so an unplugged +
        re-plugged external drive auto-resumes without an app restart.
        """
        if not self._paused:
            return
        if not self.root.exists():
            return
        logger.info("watch: root reappeared, resuming: %s", self.root)
        self.start()
```

Also update the module docstring (lines 1-18) to mention auto-resume. Replace the docstring's closing paragraph:

```
If the watch root doesn't exist at start() time, the observer marks
itself paused (``is_paused()``) and emits nothing until start() is
called again on a now-existing path.
```

with:

```
If the watch root doesn't exist at start() time, the observer marks
itself paused (``is_paused()``). Callers poll ``check_for_resume()``
on a timer; once the root reappears (e.g. an external drive is
re-mounted) it auto-resumes without requiring an app restart.
```

Now wire the poll in `app.py`. Find the block added by Task 13 (it starts `app._watch_folder = maybe_start_watch_folder(...)` then connects `aboutToQuit` to its `.stop`). Just below that block, add:

```python
    if app._watch_folder is not None:
        from PyQt6.QtCore import QTimer

        _wf_timer = QTimer()
        _wf_timer.setInterval(30_000)  # 30 s
        _wf_timer.timeout.connect(app._watch_folder.check_for_resume)
        _wf_timer.start()
        app._watch_folder_timer = _wf_timer  # keep-alive reference
        qapp.aboutToQuit.connect(_wf_timer.stop)
```

Placement is intentional: only wire the timer when a WatchFolder actually exists (disabled → `None`, no timer needed). Stash the timer on the `ParagraphosApp` instance so it doesn't get garbage-collected.

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_watch_folder.py -v`
Expected: PASS (3 existing + 2 new = 5 or more, per current baseline).

**Step 5: Full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: green.

**Step 6: Commit**

```bash
git add core/watch_folder.py app.py tests/test_watch_folder.py
git commit -m "feat(watch-folder): auto-resume when watched root re-mounts"
```

---

## Verification before calling the follow-up release done

Run each and confirm:

1. `.venv/bin/python -m pytest -q` — all green.
2. **File URI**: `.venv/bin/python -m cli episodes files --json` (after ingesting a file with a space in its path via drop) — `mp3_url` field is percent-encoded and parses with `urllib.parse.urlparse`.
3. **Drop zone responsiveness**: drop a 500 MB `.mp4` onto the running app — the window stays responsive (can drag, menus open) during the hash.
4. **URL paste responsiveness**: paste a Vimeo URL behind slow DNS — the window stays responsive during the probe.
5. **Auto-resume**: enable the watch folder in Settings, unmount the drive (external SSD), wait for the banner/pause (verified via `is_paused`), re-plug the drive, within 30 s the observer resumes and a newly-dropped file queues without a restart.

Only after all five are checked do we tag `v1.3.1`.

---

## Out of scope (deferred past these follow-ups)

- Progress bar during large-file copy in `_process_local_episode` (separate UX task; not a correctness issue).
- Multi-root watch folders (still v1.4 material per the original plan).
- Rich failure summary for `ingest_folder` (instead of silent skips) — needs a richer return type and UI changes; separate task.
- Parent-dir watchdog-based re-mount detection (QTimer polling is sufficient and simpler).
