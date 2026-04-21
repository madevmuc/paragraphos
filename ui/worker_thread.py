"""QThread-based runner for the 'Check Now' action.

Two-pass design:

* Pass 1 — refresh feeds concurrently (ThreadPoolExecutor), persist
  manifests, size the queue, and emit ``queue_sized``.
* Pass 2 — two cooperating QThreads drive the per-episode work:
  ``_DownloadPool`` fans out MP3 downloads across ``N`` worker threads
  (``settings.download_concurrency``) subject to a per-host concurrency
  cap (``settings.download_concurrency_per_host``), and pushes
  ``DownloadOutcome``s onto a bounded ``queue.Queue`` that provides
  natural backpressure. ``_TranscribeWorker`` drains the queue and runs
  whisper serially (it is CPU-bound). The two phases overlap so the
  next episode is downloading while the previous one is being
  transcribed.

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


class _DownloadPool(QThread):
    """Dispatches `pending` episodes across ``N`` download worker threads.

    The dispatcher is itself a ``QThread`` so the orchestrator can
    ``wait()`` on it exactly like before, but the per-episode work runs
    on plain ``threading.Thread`` workers pulling from a shared input
    queue. A per-host counter (``host_counter`` + ``host_lock``) still
    caps concurrent downloads against the same CDN at ``host_cap`` —
    that used to be trivially satisfied (one download at a time) and now
    actually throttles parallel fan-out across multi-CDN watchlists.

    The first emitted progress line for a show (``# slug``) previously
    relied on serial ordering. With parallel workers we guard the
    "already announced" set with a lock and emit each slug at most once,
    on whichever worker picks it up first.

    End-of-stream handling: each worker decrements a shared
    ``remaining`` counter when it exits; the worker that drops it to
    zero pushes the single ``_SHUTDOWN`` sentinel onto the transcribe
    queue. That keeps the transcribe-side drain logic unchanged (it
    still breaks on exactly one sentinel).

    ``out_q.put()`` blocking on a full queue still provides backpressure
    from the (serial) transcribe phase.
    """

    progress = pyqtSignal(str)

    def __init__(
        self,
        *,
        pending,
        pctx_for,
        out_q,
        host_counter,
        host_lock,
        host_cap: int,
        stop_flag: threading.Event,
        workers: int,
    ):
        super().__init__()
        self._pending = pending  # list[(show, ep_num, ep)]
        self._pctx_for = pctx_for  # callable(show) -> PipelineContext
        self._out_q = out_q
        self._host_counter = host_counter
        self._host_lock = host_lock
        self._host_cap = max(int(host_cap or 1), 1)
        self._stop = stop_flag
        self._n_workers = max(int(workers or 1), 1)

        # Shared dispatcher state.
        self._in_q: _queue.Queue = _queue.Queue()
        self._announced: set[str] = set()
        self._announced_lock = threading.Lock()
        self._remaining_lock = threading.Lock()
        self._remaining = self._n_workers

    def _acquire_host_slot(self, host: str) -> bool:
        """Wait (sleeping briefly) until the host has a free slot.

        Returns False if stop was requested while waiting. Called from
        plain ``threading.Thread`` workers, so we sleep on the stop
        event rather than calling ``QThread.msleep``.
        """
        while True:
            if self._stop.is_set():
                return False
            with self._host_lock:
                if self._host_counter[host] < self._host_cap:
                    self._host_counter[host] += 1
                    return True
            # Wake early if stop is set.
            if self._stop.wait(0.1):
                return False

    def _release_host_slot(self, host: str) -> None:
        with self._host_lock:
            self._host_counter[host] = max(0, self._host_counter[host] - 1)

    def _announce_show(self, slug: str) -> None:
        with self._announced_lock:
            if slug in self._announced:
                return
            self._announced.add(slug)
        self.progress.emit(f"# {slug}")

    def _worker_loop(self) -> None:
        try:
            while True:
                if self._stop.is_set():
                    self.progress.emit("stopped between episodes")
                    return
                try:
                    item = self._in_q.get_nowait()
                except _queue.Empty:
                    return
                show, ep_num, ep = item

                self._announce_show(show.slug)

                host = urlparse(ep["mp3_url"]).netloc or "?"
                if not self._acquire_host_slot(host):
                    return
                try:
                    pctx = self._pctx_for(show)
                    self.progress.emit(f"  ↓ {ep['title'][:80]}")
                    outcome: DownloadOutcome = download_phase(
                        ep["guid"], pctx, episode_number=ep_num
                    )
                finally:
                    self._release_host_slot(host)

                # Attach show/ep metadata the transcribe worker needs
                # for progress reporting (episode_done payload).
                self._out_q.put((show, ep, outcome))
        finally:
            # Only the last worker standing pushes the end-of-stream
            # sentinel so the transcribe worker sees exactly one.
            with self._remaining_lock:
                self._remaining -= 1
                last = self._remaining == 0
            if last:
                self._out_q.put(_SHUTDOWN)

    def run(self) -> None:
        # Prime the input queue once; workers drain it concurrently.
        for item in self._pending:
            self._in_q.put(item)

        threads: list[threading.Thread] = []
        for i in range(self._n_workers):
            t = threading.Thread(
                target=self._worker_loop,
                name=f"dl-worker-{i}",
                daemon=True,
            )
            t.start()
            threads.append(t)

        for t in threads:
            t.join()


class _TranscribeWorker(QThread):
    """Consumes ``DownloadOutcome``s and runs whisper sequentially.

    Emits ``episode_done`` with exactly the same 7-tuple the old serial
    code emitted — UI consumers don't know there's a new pipeline.
    """

    progress = pyqtSignal(str)
    # slug, guid, action, done_idx, total_pending, show_title, ep_title
    episode_done = pyqtSignal(str, str, str, int, int, str, str)

    def __init__(self, *, in_q, pctx_for, total: int, stop_flag: threading.Event):
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
                show.slug,
                ep["guid"],
                r.action,
                done_idx,
                self._total,
                show.title,
                ep["title"],
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

    def __init__(
        self,
        ctx,
        settings: Settings,
        *,
        only_slug: str | None = None,
        limit: int = 0,
        force: bool = False,
    ):
        super().__init__()
        self.ctx = ctx
        self.settings = settings
        self.only_slug = only_slug
        self.limit = limit
        # force=True bypasses the per-feed backoff filter in pass 1a so a
        # user-initiated Start click can retry a parked feed immediately.
        # Scheduler / background callers leave this False so the 1/3/7-day
        # backoff still protects against hammering broken feeds.
        self.force = force
        self._stop = False
        self._stop_event = threading.Event()

    def request_stop(self) -> None:
        self._stop = True
        self._stop_event.set()

    def _pctx_for(self, show) -> PipelineContext:
        """Build a PipelineContext customised for a specific show."""
        return PipelineContext(
            state=self.ctx.state,
            library=self.ctx.library,
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
        targets = [
            s for s in wl.shows if s.enabled and (not self.only_slug or s.slug == self.only_slug)
        ]

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
            if not self.force and backoff.in_backoff(self.ctx.state, show.slug):
                self.progress.emit(f"skip {show.slug} (in backoff after repeated feed failures)")
                continue
            if self.ctx.state.get_meta(f"show_paused:{show.slug}") == "1":
                self.progress.emit(f"skip {show.slug} (paused per-show)")
                continue
            fetch_targets.append(show)

        fetch_results: dict[str, tuple] = {}
        max_workers = min(max(int(self.settings.rss_concurrency or 1), 1), 16)
        if fetch_targets:
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="rss") as ex:
                future_to_show = {}
                for show in fetch_targets:
                    if self._stop:
                        break
                    stored_etag = self.ctx.state.get_meta(f"feed_etag:{show.slug}")
                    stored_modified = self.ctx.state.get_meta(f"feed_modified:{show.slug}")
                    future_to_show[
                        ex.submit(
                            build_manifest_with_url,
                            show.rss,
                            timeout=60,
                            etag=stored_etag,
                            modified=stored_modified,
                        )
                    ] = show
                for f in as_completed(future_to_show):
                    show = future_to_show[f]
                    if self._stop:
                        continue
                    try:
                        canonical, manifest, new_etag, new_modified = f.result()
                    except Exception as e:
                        fails = backoff.on_failure(self.ctx.state, show.slug)
                        self.progress.emit(f"feed error {show.slug} (fail #{fails}): {e}")
                        continue
                    backoff.on_success(self.ctx.state, show.slug)
                    if manifest is None:
                        # 304 Not Modified — skip pass-2 manifest parse
                        # entirely for this show, but still emit progress
                        # so the UI knows the feed was checked.
                        self.progress.emit(f"{show.slug}: unchanged (304) — skipping parse")
                        continue
                    if new_etag:
                        self.ctx.state.set_meta(f"feed_etag:{show.slug}", new_etag)
                    if new_modified:
                        self.ctx.state.set_meta(f"feed_modified:{show.slug}", new_modified)
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
                self.progress.emit(f"feed moved: {show.rss} → {canonical} — updating watchlist")
                show.rss = canonical
                self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
            for ep in manifest:
                self.ctx.state.upsert_episode(
                    show_slug=show.slug,
                    guid=ep["guid"],
                    title=ep["title"],
                    pub_date=ep["pubDate"],
                    mp3_url=ep["mp3_url"],
                    duration_sec=_pd(ep.get("duration", "")),
                )
            ep_num_map = {e["guid"]: e["episode_number"] for e in manifest}
            pending = self.ctx.state.list_by_status(show.slug, EpisodeStatus.PENDING)
            if self.limit:
                pending = pending[-self.limit :]
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

        dl = _DownloadPool(
            pending=all_pending,
            pctx_for=self._pctx_for,
            out_q=q,
            host_counter=host_counter,
            host_lock=host_lock,
            host_cap=host_cap,
            stop_flag=self._stop_event,
            workers=dl_conc,
        )
        tr = _TranscribeWorker(
            in_q=q,
            pctx_for=self._pctx_for,
            total=total,
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
                    self.progress.emit("queue paused mid-run — halting between episodes")
                    self._stop_event.set()
                    return
                pause_watch_stop.wait(1.0)

        pw = threading.Thread(target=_watch_pause, name="pause-watch", daemon=True)
        pw.start()

        dl.start()
        tr.start()
        dl.wait()
        tr.wait()
        pause_watch_stop.set()

        self.finished_all.emit()
