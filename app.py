"""Paragraphos — menu-bar entry point.

Uses QSystemTrayIcon (pure Qt) so the Qt event loop drives everything —
avoids the rumps/NSApp vs. Qt event-loop conflict we ran into.

Run:
    cd scripts/paragraphos
    PYTHONPATH=. ../../.venv/bin/python app.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFileOpenEvent, QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                             QFileDialog, QLineEdit, QMenu, QMessageBox,
                             QPlainTextEdit, QSystemTrayIcon, QTextEdit)

from core.logger import setup_logging  # noqa: E402
from core.paths import migrate_from_legacy, user_data_dir  # noqa: E402
from core.scheduler import should_catch_up  # noqa: E402
from ui.app_context import AppContext  # noqa: E402
from ui.first_run_wizard import show_wizard_if_needed  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.worker_thread import CheckAllThread  # noqa: E402


# One-time migration: if the repo source tree has legacy data, copy it to the
# user's Application Support dir. After that, user_data_dir() is canonical.
_LEGACY = Path(__file__).resolve().parent / "data"
_migrated = migrate_from_legacy(_LEGACY)
if _migrated:
    print(f"migrated user data to ~/Library/Application Support/Paragraphos/: "
          f"{_migrated}", flush=True)
DATA_DIR = user_data_dir()


def _build_icon() -> QIcon:
    """Bold 'P' on a filled dark circle — non-template so it's visible in both
    light and dark menu bars without relying on emoji fonts (which produce
    blank template icons on many macOS setups)."""
    size = 22
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(30, 30, 30))
    p.setPen(QColor(30, 30, 30))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.setPen(QColor(255, 255, 255))
    f = QFont("Helvetica")
    f.setPointSize(13)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), 0x84, "P")  # Qt::AlignCenter
    p.end()
    return QIcon(pm)


class ParagraphosApp(QObject):
    notify = pyqtSignal(str, str, str)  # title, subtitle, body

    def __init__(self) -> None:
        super().__init__()
        self.ctx = AppContext.load(DATA_DIR)
        setup_logging(DATA_DIR, retention_days=self.ctx.settings.log_retention_days)
        self._thread: CheckAllThread | None = None

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("ERROR: system tray not available on this system.", flush=True)
        self.tray = QSystemTrayIcon(_build_icon())
        self.tray.setToolTip("Paragraphos")
        self.tray.activated.connect(self._on_tray_activated)

        menu = QMenu()
        open_a = QAction("Open", menu); open_a.triggered.connect(self.open_window)
        check_a = QAction("Check Now", menu); check_a.triggered.connect(self._run_check)
        opml_a = QAction("Import OPML…", menu); opml_a.triggered.connect(self._import_opml)
        quit_a = QAction("Quit", menu); quit_a.triggered.connect(QApplication.quit)
        for a in (open_a, check_a):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(opml_a)
        menu.addSeparator()
        menu.addAction(quit_a)
        self.tray.setContextMenu(menu)
        self.tray.show()
        print(f"paragraphos ready — tray visible={self.tray.isVisible()}, "
              f"system-tray-available={QSystemTrayIcon.isSystemTrayAvailable()}",
              flush=True)

        # Open the window FIRST, then catch-up, so the Stop button is wired
        # via ShowsTab.start_check() instead of running headless.
        QTimer.singleShot(300, self.open_window)

        self._window: MainWindow | None = None

        # Scheduler — runs in the APScheduler BackgroundScheduler (thread).
        # The cron job calls _run_check; Qt signals marshal back to the GUI thread.
        from core.scheduler import build_scheduler
        self._sched = build_scheduler(self.ctx.settings.daily_check_time,
                                      self._run_check_on_gui_thread)
        self._sched.start()

        if self.ctx.settings.catch_up_missed and should_catch_up(
            self.ctx.state.get_meta("last_successful_check"),
            self.ctx.settings.daily_check_time,
        ):
            # Fire AFTER the window opens (300ms) so ShowsTab owns the thread.
            QTimer.singleShot(2500, self._run_check)

    def _on_tray_activated(self, reason):
        # Single-click on macOS tray opens the window; Qt's default context menu
        # still works on right-click.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_window()

    def open_window(self) -> None:
        if self._window is None:
            self._window = MainWindow()
            # If a background check was already running before the window
            # existed, hand the thread over so the Stop button works.
            if self._thread and self._thread.isRunning():
                self._window.shows_tab.attach_external_thread(self._thread)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _run_check_on_gui_thread(self) -> None:
        QTimer.singleShot(0, self._run_check)

    def _run_check(self) -> None:
        # If the window exists, delegate to ShowsTab.start_check() — that path
        # wires the Stop button correctly. Otherwise fall back to owning the
        # thread ourselves (e.g. a scheduler firing before the user opens the
        # window).
        if self._window is not None:
            started = self._window.shows_tab.start_check()
            if not started:
                self.tray.showMessage("Paragraphos", "A check is already running.")
                return
            self._thread = self._window.shows_tab._thread
        else:
            if self._thread and self._thread.isRunning():
                self.tray.showMessage("Paragraphos", "A check is already running.")
                return
            self._thread = CheckAllThread(self.ctx, self.ctx.settings)
            self._thread.start()
        # Whatever the source, connect app-level notification hooks.
        self._thread.episode_done.connect(self._on_episode_done)
        self._thread.finished_all.connect(self._on_check_done)

    def _on_episode_done(self, slug: str, guid: str, action: str,
                         done_idx: int, total: int,
                         show_title: str, ep_title: str) -> None:
        if action != "transcribed":
            return
        if not self.ctx.settings.notify_on_success:
            return
        spot_key = f"spotcheck_done:{slug}"
        title_prefix = f"{done_idx}/{total}"
        if self.ctx.state.get_meta(spot_key) != "1":
            self.ctx.state.set_meta(spot_key, "1")
            self.tray.showMessage(
                f"✅ First transcript — {show_title}",
                f"{title_prefix} — {ep_title[:80]}\n"
                f"Open in Obsidian to spot-check the whisper_prompt quality.",
            )
            return
        self.tray.showMessage(
            f"{title_prefix} — {show_title}",
            ep_title[:120],
        )

    def _on_check_done(self) -> None:
        self.ctx.state.set_meta(
            "last_successful_check",
            datetime.now(timezone.utc).isoformat(),
        )
        if self._window:
            self._window.shows_tab.refresh()

    def on_file_dropped(self, path: str) -> None:
        """Finder drag-&-drop of .opml onto Dock / app icon."""
        p = Path(path)
        if p.suffix.lower() not in (".opml", ".xml"):
            return
        self._import_opml_from_path(p)
        # Open the window so the user sees the new shows appear.
        self.open_window()

    def _import_opml_from_path(self, path: Path) -> None:
        from core.models import Show
        from core.opml import parse_opml
        from core.rss import build_manifest, feed_metadata
        try:
            entries = parse_opml(path)
        except Exception as e:
            self.tray.showMessage("OPML import failed", str(e)); return
        existing = {s.slug for s in self.ctx.watchlist.shows}
        added = 0
        for entry in entries:
            try:
                meta = feed_metadata(entry["xmlUrl"])
                manifest = build_manifest(entry["xmlUrl"], timeout=60)
            except Exception:
                continue
            slug = (meta["title"] or entry["title"]).lower().replace(" ", "-")
            if slug in existing:
                continue
            self.ctx.watchlist.shows.append(Show(
                slug=slug, title=meta["title"] or entry["title"],
                rss=entry["xmlUrl"], whisper_prompt="",
            ))
            for ep in manifest:
                self.ctx.state.upsert_episode(
                    show_slug=slug, guid=ep["guid"], title=ep["title"],
                    pub_date=ep["pubDate"], mp3_url=ep["mp3_url"])
            added += 1
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        self.tray.showMessage(
            "OPML imported",
            f"Added {added} show(s) from {path.name}")
        if self._window:
            self._window.shows_tab.refresh()

    def _import_opml(self) -> None:
        from core.models import Show
        from core.opml import parse_opml
        from core.rss import build_manifest, feed_metadata

        path, _filter = QFileDialog.getOpenFileName(
            None, "Select OPML file", str(Path.home()), "OPML (*.opml *.xml)")
        if not path:
            return
        try:
            entries = parse_opml(Path(path))
        except Exception as e:
            QMessageBox.warning(None, "OPML error", str(e)); return

        existing = {s.slug for s in self.ctx.watchlist.shows}
        added, errors = 0, []
        for entry in entries:
            try:
                meta = feed_metadata(entry["xmlUrl"])
                manifest = build_manifest(entry["xmlUrl"], timeout=60)
            except Exception as e:
                errors.append(f"{entry['title']}: {e}"); continue
            slug = (meta["title"] or entry["title"]).lower().replace(" ", "-")
            if slug in existing: continue
            self.ctx.watchlist.shows.append(Show(
                slug=slug, title=meta["title"] or entry["title"],
                rss=entry["xmlUrl"], whisper_prompt="",
            ))
            for ep in manifest:
                self.ctx.state.upsert_episode(
                    show_slug=slug, guid=ep["guid"], title=ep["title"],
                    pub_date=ep["pubDate"], mp3_url=ep["mp3_url"])
            added += 1
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        summary = f"Imported {added} new show(s)."
        if errors:
            summary += "\n\nErrors (first 10):\n" + "\n".join(errors[:10])
        QMessageBox.information(None, "OPML import", summary)


class ParagraphosQApplication(QApplication):
    """Intercepts macOS QFileOpenEvent so Finder → Dock drops of .opml files
    land inside the running app instead of launching a new instance."""

    file_opened = pyqtSignal(str)

    def event(self, e):
        if e.type() == QEvent.Type.FileOpen and isinstance(e, QFileOpenEvent):
            self.file_opened.emit(e.file())
            return True
        return super().event(e)


_INPUT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)


class _FocusClearFilter(QObject):
    """Clear focus from text/number inputs when the user clicks outside them.

    Without this, clicking on the gray background of the Settings pane leaves
    the previously-focused QLineEdit still showing a cursor — which looks like
    a bug. We only target input widgets; buttons and menus keep their normal
    focus behaviour (Qt handles those automatically on click).
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            app = QApplication.instance()
            fw = app.focusWidget() if app else None
            if fw and isinstance(fw, _INPUT_TYPES):
                try:
                    target = app.widgetAt(event.globalPosition().toPoint())
                except AttributeError:
                    target = None
                if target is not fw and not _is_descendant(target, fw):
                    fw.clearFocus()
        return False


def _is_descendant(widget, ancestor) -> bool:
    while widget is not None:
        if widget is ancestor:
            return True
        widget = widget.parent()
    return False


def main() -> int:
    qapp = ParagraphosQApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    _focus_filter = _FocusClearFilter()
    qapp.installEventFilter(_focus_filter)
    qapp._focus_filter = _focus_filter  # keep reference alive
    if not show_wizard_if_needed(qapp):
        print("First-run wizard cancelled — exiting.", flush=True)
        return 0
    app = ParagraphosApp()
    qapp.file_opened.connect(app.on_file_dropped)
    ParagraphosApp.instance = app  # keep reference
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
