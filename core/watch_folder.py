"""Watchdog-backed folder observer for the v1.3 universal-ingest feature.

Mirrors ``core.library.start_watching`` in shape. On every new file
event we:

  1. Skip non-media extensions (cheap ``_MEDIA_EXTS`` check).
  2. Debounce ``debounce_seconds`` so a file mid-write finishes before
     ffprobe looks at it.
  3. ffprobe the file; retry once after 5 s only if ffprobe *errored*
     (the file may still be being written by a slow exporter). A clean
     "no audio" result short-circuits without the retry.
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

from core import local_source
from core.local_source import (
    _MEDIA_EXTS,
    IngestError,
    ingest_file,
    slug_for_watch,
)
from core.state import StateStore

logger = logging.getLogger(__name__)

# Bound concurrent ingest workers so a user dragging hundreds of files
# into the watched root can't spawn hundreds of threads each sleeping +
# ffprobe-ing + copying in parallel. 4 is empirical: ffprobe is I/O
# dominated, the staging copy is disk-bound, and most consumer SSDs
# start thrashing past ~4 concurrent sequential reads.
_INGEST_SEMAPHORE = threading.Semaphore(4)


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

            def on_moved(self, event):
                # Many exporters (Zoom Cloud, browser downloads finalizing
                # from .crdownload, `mv` across filesystems, OBS, rsync)
                # write to a temp file and rename to the final name. That
                # fires on_moved, not on_created — without this handler
                # those drops are silently ignored.
                if event.is_directory:
                    return
                p = Path(event.dest_path)
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
        """Debounce + ffprobe gate + ingest_file.

        Runs under ``_INGEST_SEMAPHORE`` so concurrent drops queue up
        instead of stampeding. The debounce sleep, ffprobe gate, and
        ingest_file call all happen while holding a slot — this keeps
        the bound real even when the debounce itself is non-trivial.
        """
        with _INGEST_SEMAPHORE:
            time.sleep(self.debounce_seconds)
            state = local_source.probe_audio_state(p)
            if state == "no_audio":
                logger.info("watch: skipping %s — no audio stream", p)
                return
            if state == "error":
                # Writer may still be flushing the container; retry once.
                time.sleep(5.0)
                state = local_source.probe_audio_state(p)
                if state != "audio":
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
