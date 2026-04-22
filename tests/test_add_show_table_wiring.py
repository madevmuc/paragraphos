import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_app_ref = QApplication.instance() or QApplication([])
_keepalive: list = []


def _make_dialog(tmp_path):
    from ui.add_show_dialog import AddShowDialog
    from ui.app_context import AppContext

    ctx = AppContext.load(tmp_path)
    dlg = AddShowDialog(ctx, None)
    _keepalive.append(dlg)
    return dlg


def test_results_is_show_results_table(tmp_path):
    from ui.widgets.show_results_table import ShowResultsTable

    dlg = _make_dialog(tmp_path)
    assert isinstance(dlg.results, ShowResultsTable)


def test_render_matches_kicks_off_probes(tmp_path, monkeypatch):
    # Capture FeedProbeWorker instantiations.
    from core.discovery import PodcastMatch
    from ui import add_show_dialog as mod

    dlg = _make_dialog(tmp_path)
    queued = []

    class _FakeWorker:
        def __init__(self, row, url):
            queued.append((row, url))
            from PyQt6.QtCore import QObject, pyqtSignal

            class _S(QObject):
                done = pyqtSignal(tuple)

            self._s = _S()
            self.done = self._s.done

        def run(self):
            pass

    monkeypatch.setattr(mod, "FeedProbeWorker", _FakeWorker)
    # Also intercept the pool.start so we don't actually execute anything.
    monkeypatch.setattr(dlg._search_pool, "start", lambda w: None)

    matches = [
        PodcastMatch(
            title=f"S{i}",
            author="A",
            feed_url=f"https://e/{i}",
            artwork_url=None,
            itunes_collection_id=i,
        )
        for i in range(15)
    ]
    dlg._render_name_results(matches)
    # Top-10 only on initial render.
    assert [q[0] for q in queued] == list(range(10))


def test_probe_rows_dedupes(tmp_path, monkeypatch):
    from core.discovery import PodcastMatch
    from ui import add_show_dialog as mod

    dlg = _make_dialog(tmp_path)
    queued = []

    class _FakeWorker:
        def __init__(self, row, url):
            queued.append(row)
            from PyQt6.QtCore import QObject, pyqtSignal

            class _S(QObject):
                done = pyqtSignal(tuple)

            self._s = _S()
            self.done = self._s.done

        def run(self):
            pass

    monkeypatch.setattr(mod, "FeedProbeWorker", _FakeWorker)
    monkeypatch.setattr(dlg._search_pool, "start", lambda w: None)

    matches = [
        PodcastMatch(
            title=f"S{i}",
            author="A",
            feed_url=f"https://e/{i}",
            artwork_url=None,
            itunes_collection_id=i,
        )
        for i in range(5)
    ]
    dlg._render_name_results(matches)
    # Re-probing rows 0-4 must be a no-op.
    first_count = len(queued)
    dlg._probe_rows(range(5))
    assert len(queued) == first_count
