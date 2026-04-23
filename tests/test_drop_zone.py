import os
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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

    QThreadPool.globalInstance().waitForDone(3000)
    from PyQt6.QtTest import QTest

    QTest.qWait(100)

    assert len(called["calls"]) == 1
    assert called["calls"][0]["path"] == f
    assert called["calls"][0]["tid"] != called["main_thread_id"]
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
    from PyQt6.QtTest import QTest

    QTest.qWait(100)

    assert len(calls) == 1
    assert calls[0]["url"] == "https://vimeo.com/42"
    assert calls[0]["tid"] != main_tid
    assert guids == ["Vimeo:fake"]
