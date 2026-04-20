"""QThread-based runner for the 'Check Now' action.

Two-pass design:

* Pass 1 — refresh feeds concurrently (ThreadPoolExecutor), persist
  manifests, size the queue, and emit ``queue_sized``.
* Pass 2 — two cooperating QThreads drive the per-episode work:
  ``_DownloadWorker`` downloads MP3s (with a per-host concurrency cap) and
  pushes ``DownloadOutcome``s onto a bounded ``queue.Queue`` that provides
  natural backpressure. ``_TranscribeWorker`` drains the queue and runs
  whisper. The two phases overlap so the next episode is downloading while
  the previous one is being transcribed.

All outward signals emitted by ``CheckAllThread`` (``progress``,
``queue_sized``, ``episode_done``, ``finished_all``) are preserved exactly
so the existing UI / tray / queue-listener wiring in ``app.py`` and
``ui/shows_tab.py`` keeps working.
"""

from __future__ import annotations

import queue as _queue
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, pyqtSignal

from core.models import Settings, Watchlist
from core.pipeline import (
    DownloadOutcome,
    PipelineContext,
    PipelineResult,
    download_phase,
    transcribe_phase,
)
from core.rss import build_manifest_with_url
from core.state import EpisodeStatus


# Sentinel pushed onto the queue to tell the transcribe worker "no more work".
_SHUTDOWN = object()


class _DownloadWorker(QThread):
    """Pulls `pending` episodes, downloads MP3s, pushes to the transcribe queue.

    Blocks on ``out_q.put()`` when the queue is full — that backpressure
    keeps disk usage bounded even when transcription is the slow phase.
    A per-host counter (``host_counter`` + ``host_lock``) prevents more
    than ``host_cap`` concurrent downloads against the same CDN, which
    is important when two feeds share a podcast host.
    """

    progress = pyqtSignal(str)

    def __init__(self, *, pending, pctx_for, out_q, host_counter, host_lock,
                 host_cap: int, stop_flag: threading.Event):
        super().__init__()
        self._pending = pending            # list[(show, ep_num, ep)]
        self._pctx_for = pctx_for          # callable(show) -> PipelineContext
        self._out_q = out_q
        self._host_counter = host_counter
        self._host_lock = host_lock
        self._host_cap = max(int(host_cap or 1), 1)
        self._stop = stop_flag

    def _acquire_host_slot(self, host: str) -> bool:
        """Busy-wait (with msleep) until the host has a free slot. Returns
        False if stop was requested while waiting."""
        while True:
            if self._stop.is_set():
                return False
            with self._host_lock:
                if self._host_counter[host] < self._host_cap:
                    self._host_counter[host] += 1
                    return True
            self.msleep(100)

    def _release_host_slot(self, host: str) -> None:
        with self._host_lock:
            self._host_counter[host] = max(0, self._host_counter[host] - 1)

    def run(self) -> None:  # noqa: C901
        try:
            current_slug = None
            for show, ep_num, ep in self._pending:
                if self._stop.is_set():
                    self.progress.emit("stopped between episodes")
                    break
                if show.slug != current_slug:
                    self.progress.emit(f"# {show.slug}")
                    current_slug = show.slug

                host = urlparse(ep["mp3_url"]).netloc or "?"
                if not self._acquire_host_slot(host):
                    break
                try:
                    pctx = self._pctx_for(show)
                    self.progress.emit(f"  ↓ {ep['title'][:80]}")
                    outcome: DownloadOutcome = download_phase(
                        ep["guid"], pctx, episode_number=ep_num)
                finally:
                    self._release_host_slot(host)

                # Attach show/ep metadata the transcribe worker needs for
                # progress reporting (episode_done payload).
                self._out_q.put((show, ep, outcome))
        finally:
            # Always signal end-of-stream, even on exception / stop, so the
            # transcribe worker isn't left blocked on get().
            self._out_q.put(_SHUTDOWN)


class _TranscribeWorker(QThread):
    """Consumes ``DownloadOutcome``s and runs whisper sequentially.

    Emits ``episode_done`` with exactly the same 7-tuple the old serial
    code emitted — UI consumers don't know there's a new pipeline.
    """

    progress = pyqtSignal(str)
    # slug, guid, action, done_idx, total_pending, show_title, ep_title
    episode_done = pyqtSignal(str, str, str, int, int, str, str)

    def __init__(self, *, in_q, pctx_for, total: int,
                 stop_flag: threading.Event):
        super().__init__()
        self._in_q = in_q
        self._pctx_for = pctx_for
        self._total = total
        self._stop = stop_flag

    def run(self) -> None:
        done_idx = 0
        while True:
            # A timeout-based get so we periodically notice stop_flag even
            # when the download side is stuck.
            try:
                item = self._in_q.get(timeout=0.5)
            except _queue.Empty:
                if self._stop.is_set():
                    break
                continue
            if item is _SHUTDOWN:
                break

            show, ep, outcome = item

            if outcome.result is not None:
                # Terminal already (skipped via dedup, or download failed).
                r: PipelineResult = outcome.result
            else:
                self.progress.emit(f"  → {ep['title'][:80]}")
                pctx = self._pctx_for(show)
                try:
                    r = transcribe_phase(outcome, pctx)
                except Exception as e:  # defensive — transcribe_phase
                    # should turn errors into PipelineResult, but guard.
                    r = PipelineResult("failed", outcome.guid, str(e))

            done_idx += 1
            if r.action == "failed":
                self.progress.emit(f"    [{r.action}]")
                for line in r.detail.splitlines():
                    self.progress.emit(f"        {line}")
            else:
                self.progress.emit(f"    [{r.action}] {r.detail[:160]}")
            self.episode_done.emit(
                show.slug, ep["guid"], r.action,
                done_idx, self._total, show.title, ep["title"],
            )

            if self._stop.is_set():
                # Drain without processing further work items, but keep
                # reading until the sentinel so the download worker can
                # exit cleanly.
                while True:
                    try:
                        nxt = self._in_q.get(timeout=0.5)
                    except _queue.Empty:
                        continue
                    if nxt is _SHUTDOWN:
                        return


class CheckAllThread(QThread):
    progress = pyqtSignal(str)
    # slug, guid, action, done_idx, total_pending, show_title, ep_title
    episode_done = pyqtSignal(str, str, str, int, int, str, str)
    queue_sized = pyqtSignal(int)
    finished_all = pyqtSignal()

    def __init__(self, ctx, settings: Settings, *, only_slug: str | None = None,
                 limit: int = 0):
        super().__init__()
        self.ctx = ctx
        self.settings = settings
        self.only_slug = only_slug
        self.limit = limit
        self._stop = False
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop = True
        self._stop_event.set()

    def _pctx_for(self, show) -> PipelineContext:
        """Build a PipelineContext customised for a specific show."""
        return PipelineContext(
            state=self.ctx.state, library=self.ctx.library,
            output_root=Path(self.settings.output_root).expanduser(),
            whisper_prompt=show.whisper_prompt,
            retention_days=self.settings.mp3_retention_days,
            delete_mp3_after=self.settings.delete_mp3_after_transcribe,
            language=show.language,
            model_name=self.settings.whisper_model,
            fast_mode=self.settings.whisper_fast_mode,
            processors=self.settings.whisper_multiproc,
        )

    def run(self) -> None:
        wl: Watchlist = self.ctx.watchlist
        targets = [s for s in wl.shows if s.enabled and
                   (not self.only_slug or s.slug == self.only_slug)]

        # Respect a persisted "paused" flag — if set, bail out cleanly.
        if self.ctx.state.get_meta("queue_paused") == "1":
            self.progress.emit("queue is paused — click Resume in Shows tab")
            self.finished_all.emit()
            return

        from core import backoff

        # Pass 1a: filter out skipped shows, then fetch feeds concurrently.
        fetch_targets = []
        for show in targets:
            if self._stop:
                break
            if backoff.in_backoff(self.ctx.state, show.slug):
                self.progress.emit(
                    f"skip {show.slug} (in backoff after repeated feed failures)")
                continue
            if self.ctx.state.get_meta(f"show_paused:{show.slug}") == "1":
                self.progress.emit(f"skip {show.slug} (paused per-show)")
                continue
            fetch_targets.append(show)

        fetch_results: dict[str, tuple] = {}
        max_workers = min(max(int(self.settings.rss_concurrency or 1), 1), 16)
        if fetch_targets:
            with ThreadPoolExecutor(max_workers=max_workers,
                                    thread_name_prefix="rss") as ex:
                future_to_show = {}
                for show in fetch_targets:
                    if self._stop:
                        break
                    stored_etag = self.ctx.state.get_meta(
                        f"feed_etag:{show.slug}")
                    stored_modified = self.ctx.state.get_meta(
                        f"feed_modified:{show.slug}")
                    future_to_show[
                        ex.submit(build_manifest_with_url, show.rss,
                                  timeout=60, etag=stored_etag,
                                  modified=stored_modified)
                    ] = show
                for f in as_completed(future_to_show):
                    show = future_to_show[f]
                    if self._stop:
                        continue
                    try:
                        canonical, manifest, new_etag, new_modified = f.result()
                    except Exception as e:
                        fails = backoff.on_failure(self.ctx.state, show.slug)
                        self.progress.emit(
                            f"feed error {show.slug} (fail #{fails}): {e}")
                        continue
                    backoff.on_success(self.ctx.state, show.slug)
                    if manifest is None:
                        # 304 Not Modified — skip pass-2 manifest parse
                        # entirely for this show, but still emit progress
                        # so the UI knows the feed was checked.
                        self.progress.emit(
                            f"{show.slug}: unchanged (304) — skipping parse")
                        continue
                    if new_etag:
                        self.ctx.state.set_meta(
                            f"feed_etag:{show.slug}", new_etag)
                    if new_modified:
                        self.ctx.state.set_meta(
                            f"feed_modified:{show.slug}", new_modified)
                    fetch_results[show.slug] = (show, canonical, manifest)

        # Pass 1b: persist redirects, upsert episodes, gather pending.
        from core.stats import _parse_duration as _pd
        all_pending: list[tuple] = []
        for show in fetch_targets:
            if self._stop:
                break
            res = fetch_results.get(show.slug)
            if res is None:
                continue
            _, canonical, manifest = res
            if canonical and canonical != show.rss:
                self.progress.emit(
                    f"feed moved: {show.rss} → {canonical} — updating watchlist")
                show.rss = canonical
                self.ctx.watchlist.save(
                    self.ctx.data_dir / "watchlist.yaml")
            for ep in manifest:
                self.ctx.state.upsert_episode(
                    show_slug=show.slug, guid=ep["guid"], title=ep["title"],
                    pub_date=ep["pubDate"], mp3_url=ep["mp3_url"],
                    duration_sec=_pd(ep.get("duration", "")),
                )
            ep_num_map = {e["guid"]: e["episode_number"] for e in manifest}
            pending = self.ctx.state.list_by_status(show.slug, EpisodeStatus.PENDING)
            if self.limit:
                pending = pending[-self.limit:]
            for ep in pending:
                all_pending.append((show, ep_num_map.get(ep["guid"], "0000"), ep))

        total = len(all_pending)
        self.queue_sized.emit(total)
        self.progress.emit(f"queue sized: {total} episode(s) pending")

        if total == 0 or self._stop:
            self.finished_all.emit()
            return

        # Check the persisted pause flag one more time before kicking
        # off the pipeline (matches pre-existing behaviour).
        if self.ctx.state.get_meta("queue_paused") == "1":
            self.progress.emit("queue paused mid-run — halting before pipeline")
            self.finished_all.emit()
            return

        # Pass 2: parallel download + transcribe.
        dl_conc = max(int(self.settings.download_concurrency or 1), 1)
        host_cap = max(int(self.settings.download_concurrency_per_host or 1), 1)
        host_counter: defaultdict[str, int] = defaultdict(int)
        host_lock = threading.Lock()
        q: _queue.Queue = _queue.Queue(maxsize=dl_conc)

        dl = _DownloadWorker(
            pending=all_pending, pctx_for=self._pctx_for, out_q=q,
            host_counter=host_counter, host_lock=host_lock,
            host_cap=host_cap, stop_flag=self._stop_event,
        )
        tr = _TranscribeWorker(
            in_q=q, pctx_for=self._pctx_for, total=total,
            stop_flag=self._stop_event,
        )
        # Re-emit child signals on this thread so existing wiring stays valid.
        dl.progress.connect(self.progress.emit)
        tr.progress.connect(self.progress.emit)
        tr.episode_done.connect(self.episode_done.emit)

        # Poll the persisted pause flag from a short helper thread — when
        # set we trip the shared stop event, draining both workers.
        pause_watch_stop = threading.Event()

        def _watch_pause():
            while not pause_watch_stop.is_set():
                if self.ctx.state.get_meta("queue_paused") == "1":
                    self.progress.emit(
                        "queue paused mid-run — halting between episodes")
                    self._stop_event.set()
                    return
                pause_watch_stop.wait(1.0)

        pw = threading.Thread(target=_watch_pause, name="pause-watch",
                              daemon=True)
        pw.start()

        dl.start()
        tr.start()
        dl.wait()
        tr.wait()
        pause_watch_stop.set()

        self.finished_all.emit()
