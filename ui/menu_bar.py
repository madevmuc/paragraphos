"""Full macOS menu bar: File / Edit / View / Actions / Window / Help.

Bound to MainWindow methods. Actions that map to existing buttons (Check Now,
Stop, etc.) delegate to shows_tab; others live on MainWindow directly.
"""

from __future__ import annotations

import webbrowser
from pathlib import Path

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QApplication, QMenuBar


def build_menu_bar(window) -> QMenuBar:
    mb = QMenuBar(window)
    mb.setNativeMenuBar(True)

    # ── File ──────────────────────────────────────────────────────
    f = mb.addMenu("File")
    a = QAction("Add Podcast…", window); a.setShortcut("Ctrl+N")
    a.triggered.connect(window.shows_tab._add); f.addAction(a)
    a = QAction("Add Episodes…", window); a.setShortcut("Ctrl+Shift+N")
    a.triggered.connect(window.shows_tab._curated); f.addAction(a)
    a = QAction("Import OPML…", window); a.setShortcut("Ctrl+Shift+I")
    a.triggered.connect(lambda: _import_opml(window)); f.addAction(a)
    a = QAction("Export Show…", window); a.setShortcut("Ctrl+Shift+E")
    a.triggered.connect(lambda: _export_show(window)); f.addAction(a)
    f.addSeparator()
    a = QAction("Open Latest Transcript", window); a.setShortcut("Ctrl+O")
    a.triggered.connect(lambda: _open_latest(window)); f.addAction(a)
    a = QAction("Reveal Output in Finder", window); a.setShortcut("Ctrl+Shift+F")
    a.triggered.connect(lambda: _reveal_output(window)); f.addAction(a)
    f.addSeparator()
    a = QAction("Close", window); a.setShortcut("Ctrl+W")
    a.triggered.connect(window.close); f.addAction(a)

    # ── Edit ──────────────────────────────────────────────────────
    e = mb.addMenu("Edit")
    for label, key in (("Undo", "Ctrl+Z"), ("Redo", "Ctrl+Shift+Z"),
                       ("Cut", "Ctrl+X"), ("Copy", "Ctrl+C"),
                       ("Paste", "Ctrl+V"), ("Select All", "Ctrl+A")):
        a = QAction(label, window); a.setShortcut(key); e.addAction(a)
    e.addSeparator()
    a = QAction("Settings…", window); a.setShortcut(QKeySequence.StandardKey.Preferences)
    a.triggered.connect(lambda: _focus_tab(window, 2)); e.addAction(a)

    # ── View ──────────────────────────────────────────────────────
    v = mb.addMenu("View")
    for label, key, tab_idx in (("Shows Tab", "Ctrl+1", 0),
                                 ("Queue Tab", "Ctrl+2", 1),
                                 ("Failed Tab", "Ctrl+3", 2),
                                 ("Settings Tab", "Ctrl+4", 3)):
        a = QAction(label, window); a.setShortcut(key)
        a.triggered.connect(lambda _=False, i=tab_idx: _focus_tab(window, i))
        v.addAction(a)
    v.addSeparator()
    a = QAction("Show/Hide Log", window); a.setShortcut("Ctrl+L")
    a.triggered.connect(lambda: window.log_dock.setVisible(not window.log_dock.isVisible()))
    v.addAction(a)
    a = QAction("Enter Full Screen", window); a.setShortcut("Ctrl+Meta+F")
    a.triggered.connect(lambda: window.setWindowState(
        window.windowState() ^ window.windowState().__class__.WindowFullScreen))
    v.addAction(a)

    # ── Actions ───────────────────────────────────────────────────
    ac = mb.addMenu("Actions")
    a = QAction("Check Now", window); a.setShortcut("Ctrl+R")
    a.triggered.connect(lambda: window.shows_tab.start_check()); ac.addAction(a)
    a = QAction("Check Selected Show", window); a.setShortcut("Ctrl+Shift+R")
    a.triggered.connect(lambda: _check_selected(window)); ac.addAction(a)
    a = QAction("Stop", window); a.setShortcut("Ctrl+.")
    a.triggered.connect(window.shows_tab._stop); ac.addAction(a)
    a = QAction("Pause Queue", window); a.setShortcut("Ctrl+P")
    a.triggered.connect(lambda: window.shows_tab._pause()); ac.addAction(a)
    a = QAction("Resume Queue", window); a.setShortcut("Ctrl+Shift+P")
    a.triggered.connect(lambda: window.shows_tab._resume()); ac.addAction(a)
    ac.addSeparator()
    a = QAction("Mark Selected Show Stale", window)
    a.triggered.connect(lambda: _mark_selected_stale(window)); ac.addAction(a)
    a = QAction("Retry Selected (Failed)", window)
    a.triggered.connect(lambda: _focus_tab(window, 1)); ac.addAction(a)
    a = QAction("Open Latest in Obsidian", window)
    a.triggered.connect(lambda: _open_in_obsidian(window)); ac.addAction(a)

    # ── Window ────────────────────────────────────────────────────
    w = mb.addMenu("Window")
    a = QAction("Minimize", window); a.setShortcut("Ctrl+M")
    a.triggered.connect(window.showMinimized); w.addAction(a)
    a = QAction("Zoom", window); a.triggered.connect(window.showMaximized); w.addAction(a)

    # ── Help ──────────────────────────────────────────────────────
    h = mb.addMenu("Help")
    a = QAction("Paragraphos Help", window)
    a.triggered.connect(lambda: webbrowser.open("https://github.com/"))
    h.addAction(a)
    a = QAction("Keyboard Shortcuts", window)
    a.triggered.connect(lambda: _show_shortcuts(window)); h.addAction(a)
    a = QAction("About Paragraphos", window)
    a.triggered.connect(lambda: _show_about(window)); h.addAction(a)
    a = QAction("Changelog", window)
    a.triggered.connect(lambda: _show_changelog(window)); h.addAction(a)
    a = QAction("Show Log Folder", window)
    a.triggered.connect(lambda: _open_log_folder(window)); h.addAction(a)

    return mb


# ── helpers ───────────────────────────────────────────────────────

def _focus_tab(window, idx: int) -> None:
    window.tabs.setCurrentIndex(idx)


def _import_opml(window) -> None:
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from core.models import Show
    from core.opml import parse_opml
    from core.rss import build_manifest, feed_metadata

    path, _ = QFileDialog.getOpenFileName(
        window, "Select OPML", str(Path.home()), "OPML (*.opml *.xml)")
    if not path:
        return
    try:
        entries = parse_opml(Path(path))
    except Exception as ex:
        QMessageBox.warning(window, "OPML error", str(ex)); return
    existing = {s.slug for s in window.ctx.watchlist.shows}
    added = 0; errs: list[str] = []
    for entry in entries:
        try:
            meta = feed_metadata(entry["xmlUrl"])
            manifest = build_manifest(entry["xmlUrl"], timeout=60)
        except Exception as ex:
            errs.append(f"{entry['title']}: {ex}"); continue
        slug = (meta["title"] or entry["title"]).lower().replace(" ", "-")
        if slug in existing:
            continue
        window.ctx.watchlist.shows.append(Show(
            slug=slug, title=meta["title"] or entry["title"],
            rss=entry["xmlUrl"], whisper_prompt="",
        ))
        for ep in manifest:
            window.ctx.state.upsert_episode(
                show_slug=slug, guid=ep["guid"], title=ep["title"],
                pub_date=ep["pubDate"], mp3_url=ep["mp3_url"])
        added += 1
    window.ctx.watchlist.save(window.ctx.data_dir / "watchlist.yaml")
    window.shows_tab.refresh()
    QMessageBox.information(window, "OPML import",
                            f"Added {added} show(s)." +
                            ("\n\nErrors:\n" + "\n".join(errs[:10]) if errs else ""))


def _selected_slug(window) -> str | None:
    rows = window.shows_tab.table.selectedIndexes()
    if not rows:
        return None
    return window.shows_tab.table.item(rows[0].row(), 0).text()


def _check_selected(window) -> None:
    slug = _selected_slug(window)
    if slug:
        window.shows_tab.start_check(only_slug=slug)


def _mark_selected_stale(window) -> None:
    slug = _selected_slug(window)
    if slug:
        window.shows_tab._mark_stale(slug)


def _export_show(window) -> None:
    from core.export import export_show
    from PyQt6.QtWidgets import QMessageBox
    slug = _selected_slug(window)
    if not slug:
        QMessageBox.information(window, "Select show",
                                "Select a row in the Shows tab first.")
        return
    output_root = Path(window.ctx.settings.output_root).expanduser()
    export_dir = Path(window.ctx.settings.export_root).expanduser()
    zip_path = export_show(slug, output_root, export_dir)
    QMessageBox.information(window, "Exported", f"Wrote {zip_path}")


def _open_latest(window) -> None:
    import subprocess
    slug = _selected_slug(window)
    if not slug:
        return
    show_dir = Path(window.ctx.settings.output_root).expanduser() / slug
    mds = sorted(show_dir.glob("*.md"))
    if not mds:
        return
    subprocess.run(["open", str(mds[-1])])


def _reveal_output(window) -> None:
    import subprocess
    subprocess.run(["open", str(Path(window.ctx.settings.output_root).expanduser())])


def _open_in_obsidian(window) -> None:
    slug = _selected_slug(window)
    if not slug:
        return
    vault = Path(window.ctx.settings.obsidian_vault_path).expanduser()
    output_root = Path(window.ctx.settings.output_root).expanduser()
    show_dir = output_root / slug
    mds = sorted(show_dir.glob("*.md"))
    if not mds:
        return
    try:
        rel = mds[-1].relative_to(vault)
    except ValueError:
        # Not inside the vault → open in default macOS app instead.
        import subprocess; subprocess.run(["open", str(mds[-1])]); return
    import urllib.parse
    url = (f"obsidian://open?vault={urllib.parse.quote(window.ctx.settings.obsidian_vault_name)}"
           f"&file={urllib.parse.quote(str(rel))}")
    webbrowser.open(url)


def _show_about(window) -> None:
    from ui.about_dialog import AboutDialog
    AboutDialog(window).exec()


def _show_changelog(window) -> None:
    from ui.about_dialog import ChangelogDialog
    ChangelogDialog(window).exec()


def _show_shortcuts(window) -> None:
    from PyQt6.QtWidgets import QMessageBox
    QMessageBox.information(window, "Shortcuts",
        "⌘N     Add Podcast\n"
        "⌘⇧N    Add Episodes\n"
        "⌘⇧I    Import OPML\n"
        "⌘,     Settings\n"
        "⌘R     Check Now\n"
        "⌘⇧R    Check Selected Show\n"
        "⌘.     Stop\n"
        "⌘P/⌘⇧P Pause / Resume\n"
        "⌘1–4   Jump between tabs\n"
        "⌘L     Toggle Log\n"
        "⌘O     Open Latest Transcript\n"
        "⌘⇧F    Reveal Output in Finder\n"
    )


def _open_log_folder(window) -> None:
    import subprocess
    logs = window.ctx.data_dir / "logs"
    logs.mkdir(exist_ok=True)
    subprocess.run(["open", str(logs)])
