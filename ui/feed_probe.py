"""Lightweight feed probe for the search-results table.

Fetches a single RSS feed in a background thread (via QThreadPool) and
emits a single tuple signal with (row_index, ep_count, latest_iso_date,
latest_title). Failures emit (row_index, None, None, None) so the table
can render an em-dash instead of hanging on a dead host.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from core.rss import build_manifest_with_url as fetch_feed


class _Signals(QObject):
    done = pyqtSignal(tuple)  # (row_index, ep_count|None, latest_date|None, latest_title|None)


class FeedProbeWorker(QRunnable):
    def __init__(self, row_index: int, feed_url: str):
        super().__init__()
        self._row = row_index
        self._url = feed_url
        self._signals = _Signals()
        self.done = self._signals.done

    def run(self) -> None:
        try:
            _, manifest, _, _ = fetch_feed(self._url, timeout=8.0)
            if not manifest:
                self._signals.done.emit((self._row, 0, None, None))
                return
            latest = manifest[-1]
            self._signals.done.emit((self._row, len(manifest), latest["pubDate"], latest["title"]))
        except Exception:
            self._signals.done.emit((self._row, None, None, None))
