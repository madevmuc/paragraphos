"""Tests for ui/drop_zone.py — file + URL ingest dispatch."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_drop_zone_accepts_file_uri(tmp_path: Path, monkeypatch):
    import PyQt6.QtWidgets as qtw

    _ = qtw.QApplication.instance() or qtw.QApplication([])

    from core.state import StateStore
    from ui.drop_zone import DropZone

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    (tmp_path / "watchlist.yaml").write_text("shows: []\n", encoding="utf-8")

    captured = {}

    def fake_ingest_file(path, **kw):
        captured["path"] = Path(path)
        return "sha256:fake"

    monkeypatch.setattr("ui.drop_zone.ingest_file", fake_ingest_file)

    dz = DropZone(
        state=state,
        watchlist_path=tmp_path / "watchlist.yaml",
        max_duration_hours=4,
    )
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")
    dz.handle_paths([f])
    assert captured["path"] == f


def test_drop_zone_accepts_url_text(tmp_path: Path, monkeypatch):
    import PyQt6.QtWidgets as qtw

    _ = qtw.QApplication.instance() or qtw.QApplication([])

    from core.state import StateStore
    from ui.drop_zone import DropZone

    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    (tmp_path / "watchlist.yaml").write_text("shows: []\n", encoding="utf-8")

    captured = {}

    def fake_ingest_url(url, **kw):
        captured["url"] = url
        return "Vimeo:abc"

    monkeypatch.setattr("ui.drop_zone.ingest_url", fake_ingest_url)

    dz = DropZone(
        state=state,
        watchlist_path=tmp_path / "watchlist.yaml",
        max_duration_hours=4,
    )
    dz.handle_url("https://vimeo.com/42")
    assert captured["url"] == "https://vimeo.com/42"
