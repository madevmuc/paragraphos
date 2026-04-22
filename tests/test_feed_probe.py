import os
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication

from ui.feed_probe import FeedProbeWorker


def _pump(app, received, timeout=2.0):
    deadline = time.time() + timeout
    while not received and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)


def test_probe_emits_success_tuple():
    app = QCoreApplication.instance() or QCoreApplication([])
    manifest = [
        {"guid": "a", "title": "Old", "pubDate": "2024-01-01T00:00:00"},
        {"guid": "b", "title": "Mid", "pubDate": "2024-06-01T00:00:00"},
        {"guid": "c", "title": "New", "pubDate": "2024-12-01T00:00:00"},
    ]
    received = []
    worker = FeedProbeWorker(row_index=3, feed_url="https://e/r")
    worker.done.connect(lambda tup: received.append(tup))
    with patch(
        "ui.feed_probe.fetch_feed", lambda url, timeout=10.0: ("canon", manifest, None, None)
    ):
        worker.run()
    _pump(app, received)
    assert received == [(3, 3, "2024-12-01T00:00:00", "New")]


def test_probe_emits_zero_when_manifest_empty():
    app = QCoreApplication.instance() or QCoreApplication([])
    received = []
    worker = FeedProbeWorker(row_index=5, feed_url="https://e/r")
    worker.done.connect(lambda tup: received.append(tup))
    with patch("ui.feed_probe.fetch_feed", lambda url, timeout=10.0: ("canon", [], None, None)):
        worker.run()
    _pump(app, received)
    assert received == [(5, 0, None, None)]


def test_probe_emits_failure_tuple_on_exception():
    app = QCoreApplication.instance() or QCoreApplication([])
    received = []
    worker = FeedProbeWorker(row_index=7, feed_url="https://broken")
    worker.done.connect(lambda tup: received.append(tup))

    def boom(url, timeout=10.0):
        raise RuntimeError("network timeout")

    with patch("ui.feed_probe.fetch_feed", boom):
        worker.run()
    _pump(app, received)
    assert received == [(7, None, None, None)]
