"""QThread-based runner for the 'Check Now' action.

Two-pass design: pass 1 refreshes manifests + computes total queue size (so
the UI knows `done/total` for progress + ETA). Pass 2 processes episodes one
by one with between-episode stop-checkpoints. Progress signals feed the log
dock; episode_done carries the full counter for notifications + queue-status
widget.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

from core.models import Settings, Watchlist
from core.pipeline import PipelineContext, process_episode
from core.rss import build_manifest_with_url
from core.state import EpisodeStatus


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

    def request_stop(self) -> None:
        self._stop = True

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

        # Pass 1a: filter out skipped shows (backoff / per-show pause),
        # then fetch all remaining feeds concurrently. The network I/O
        # is the bottleneck — parallelising it cuts wall-clock time
        # for "Check Now" with many feeds from O(N × RTT) to O(RTT).
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

        # results: {slug: (show, canonical_url, manifest)} — preserves
        # ordering-independent mapping for the sequential pass 1b below.
        fetch_results: dict[str, tuple] = {}
        max_workers = min(max(int(self.settings.rss_concurrency or 1), 1), 16)
        if fetch_targets:
            with ThreadPoolExecutor(max_workers=max_workers,
                                    thread_name_prefix="rss") as ex:
                future_to_show = {}
                for show in fetch_targets:
                    if self._stop:
                        break
                    future_to_show[
                        ex.submit(build_manifest_with_url, show.rss, timeout=60)
                    ] = show
                for f in as_completed(future_to_show):
                    show = future_to_show[f]
                    if self._stop:
                        # let remaining futures finish naturally; don't
                        # cancel mid-flight (httpx client handles it)
                        continue
                    try:
                        canonical, manifest = f.result()
                    except Exception as e:
                        fails = backoff.on_failure(self.ctx.state, show.slug)
                        self.progress.emit(
                            f"feed error {show.slug} (fail #{fails}): {e}")
                        continue
                    backoff.on_success(self.ctx.state, show.slug)
                    fetch_results[show.slug] = (show, canonical, manifest)

        # Pass 1b: persist redirects, upsert episodes, gather pending.
        # Runs sequentially on the main worker thread so SQLite writes
        # and watchlist.yaml saves stay single-writer.
        from core.stats import _parse_duration as _pd
        all_pending: list[tuple] = []
        # Iterate in the original target order for deterministic logs.
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

        # Pass 2: process.
        current_slug = None
        done_idx = 0
        for show, ep_num, ep in all_pending:
            if self._stop:
                self.progress.emit("stopped between episodes")
                break
            if self.ctx.state.get_meta("queue_paused") == "1":
                self.progress.emit("queue paused mid-run — halting between episodes")
                break
            if show.slug != current_slug:
                self.progress.emit(f"# {show.slug}")
                current_slug = show.slug
            pctx = PipelineContext(
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
            self.progress.emit(f"  → {ep['title'][:80]}")
            r = process_episode(ep["guid"], pctx, episode_number=ep_num)
            done_idx += 1
            # Show full multi-line detail on failure — the old single-line
            # truncation hid the specific cause (paths, stderr, etc.) that
            # actually helps debug.
            if r.action == "failed":
                self.progress.emit(f"    [{r.action}]")
                for line in r.detail.splitlines():
                    self.progress.emit(f"        {line}")
            else:
                self.progress.emit(f"    [{r.action}] {r.detail[:160]}")
            self.episode_done.emit(show.slug, ep["guid"], r.action,
                                   done_idx, total, show.title, ep["title"])
        self.finished_all.emit()
