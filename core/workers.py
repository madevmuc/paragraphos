"""Worker pool wrapping concurrent.futures with gather + cancel-on-stop."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any, Callable, List


class WorkerPool:
    """Thread pool — fine for our I/O-bound and single-whisper-subprocess workload.

    We do NOT use ProcessPoolExecutor because whisper-cli itself is a subprocess
    and runs at full CPU/GPU — running more than one at a time is the user's
    explicit opt-in via settings.parallel_transcribe. Threads are sufficient
    for supervising those subprocesses.
    """

    def __init__(self, max_workers: int = 1):
        self._ex = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        return self._ex.submit(fn, *args, **kwargs)

    def gather(self, futures: List[Future]) -> List[Any]:
        results: List[Any] = []
        for f in as_completed(futures):
            results.append(f.result())
        return results

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        self._ex.shutdown(wait=wait, cancel_futures=cancel_pending)
