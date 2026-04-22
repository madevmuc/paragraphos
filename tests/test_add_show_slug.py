import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

_app_ref = None
_dialog_refs: list = []


def _make_dialog(tmp_path):
    global _app_ref
    _app_ref = QApplication.instance() or QApplication([])
    from ui.add_show_dialog import AddShowDialog
    from ui.app_context import AppContext

    ctx = AppContext.load(tmp_path)
    dlg = AddShowDialog(ctx, None)
    _dialog_refs.append(dlg)
    return dlg


def test_name_path_default_slug_uses_slugify(tmp_path):
    dlg = _make_dialog(tmp_path)
    # Simulate _pick_name_result body (slug write) with a punctuation-heavy title.
    meta = {"title": "Die Drei ???! Folge 1", "author": "Europa"}
    from core.sanitize import slugify

    dlg.name_slug.setText(slugify(meta["title"] or ""))
    assert dlg.name_slug.text() == "die-drei-folge-1"


def test_url_path_sets_slugify_slug(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path)
    dlg._loaded_meta = {"title": "Tech! Podcast — Show", "author": "Host"}
    dlg._loaded_manifest = []
    dlg._loaded_rss = "https://e/r"
    captured = {}
    # Spy on _do_save — it's the funnel.
    monkeypatch.setattr(dlg, "_do_save", lambda show: captured.update(show))
    dlg._add_from_url()
    assert captured["slug"] == "tech-podcast-show"


def test_apple_path_sets_slugify_slug(tmp_path, monkeypatch):
    dlg = _make_dialog(tmp_path)
    dlg._loaded_meta = {"title": "Darknet: Diaries — Jack", "author": "Jack"}
    dlg._loaded_manifest = []
    dlg._loaded_rss = "https://e/r"
    captured = {}
    monkeypatch.setattr(dlg, "_do_save", lambda show: captured.update(show))
    dlg._add_from_apple()
    assert captured["slug"] == "darknet-diaries-jack"
