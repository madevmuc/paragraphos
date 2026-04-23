import os
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Keep Qt widgets + QApplication alive across tests. pytest aggressively GCs
# locals between assertions; without this, the C++ Qt object backing the
# LocalTranscriptTab can be freed before the signal is connected.
_QT_KEEPALIVE: list = []


def _make_tab(tmp_path: Path):
    import PyQt6.QtWidgets as qtw

    app = qtw.QApplication.instance() or qtw.QApplication([])
    _QT_KEEPALIVE.append(app)
    from ui.app_context import AppContext
    from ui.local_transcript_tab import LocalTranscriptTab

    ctx = AppContext.load(tmp_path)
    _QT_KEEPALIVE.append(ctx)
    tab = LocalTranscriptTab(ctx)
    _QT_KEEPALIVE.append(tab)
    return tab, ctx


def test_local_transcript_tab_ingests_files_off_main_thread(tmp_path: Path, monkeypatch):
    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtTest import QTest

    tab, _ctx = _make_tab(tmp_path)

    called = {"main_tid": threading.get_ident(), "tids": []}

    def fake_ingest_file(path, **kw):
        called["tids"].append(threading.get_ident())
        return "sha256:fake"

    monkeypatch.setattr("ui.local_transcript_tab.ingest_file", fake_ingest_file)

    guids: list[str] = []
    tab.ingested.connect(guids.append)

    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    tab.handle_paths([f])

    QThreadPool.globalInstance().waitForDone(3000)
    QTest.qWait(100)

    assert len(called["tids"]) == 1
    assert called["tids"][0] != called["main_tid"]
    assert guids == ["sha256:fake"]


def test_local_transcript_tab_ingests_url_off_main_thread(tmp_path: Path, monkeypatch):
    from PyQt6.QtCore import QThreadPool
    from PyQt6.QtTest import QTest

    tab, _ctx = _make_tab(tmp_path)

    main_tid = threading.get_ident()
    tids: list[int] = []

    def fake_ingest_url(url, **kw):
        tids.append(threading.get_ident())
        return "Vimeo:fake"

    monkeypatch.setattr("ui.local_transcript_tab.ingest_url", fake_ingest_url)

    guids: list[str] = []
    tab.ingested.connect(guids.append)

    tab.handle_url("https://vimeo.com/42")

    QThreadPool.globalInstance().waitForDone(3000)
    QTest.qWait(100)

    assert len(tids) == 1
    assert tids[0] != main_tid
    assert guids == ["Vimeo:fake"]
