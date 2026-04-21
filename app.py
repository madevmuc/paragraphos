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
from PyQt6.QtGui import QColor, QFileOpenEvent, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSystemTrayIcon,
    QTextEdit,
)

from core.logger import setup_logging  # noqa: E402
from core.paths import migrate_from_legacy, user_data_dir  # noqa: E402
from core.scheduler import should_catch_up  # noqa: E402
from core.version import VERSION as _LOCAL_VERSION  # noqa: E402
from ui.app_context import AppContext  # noqa: E402
from ui.first_run_wizard import show_wizard_if_needed  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.worker_thread import CheckAllThread  # noqa: E402

# One-time migration: if the repo source tree has legacy data, copy it to the
# user's Application Support dir. After that, user_data_dir() is canonical.
_LEGACY = Path(__file__).resolve().parent / "data"
_migrated = migrate_from_legacy(_LEGACY)
if _migrated:
    print(
        f"migrated user data to ~/Library/Application Support/Paragraphos/: {_migrated}",
        flush=True,
    )
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
    update_available = pyqtSignal(str, str)  # tag, html_url — GUI-thread safe

    def __init__(self) -> None:
        super().__init__()
        self.ctx = AppContext.load(DATA_DIR)
        setup_logging(DATA_DIR, retention_days=self.ctx.settings.log_retention_days)
        self._thread: CheckAllThread | None = None
        self._run_tally: dict[str, object] = {}

        # Non-blocking update check against GitHub releases. Runs in a
        # daemon thread; emit through a signal so the UI sees it on the GUI
        # thread regardless of where the HTTP callback fires.
        from core.updater import check_for_update

        self.update_available.connect(self._on_update_available)
        check_for_update(
            local_version=_LOCAL_VERSION,
            on_update_available=lambda tag, url: self.update_available.emit(tag, url),
            repo=self.ctx.settings.github_repo,
        )

        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("ERROR: system tray not available on this system.", flush=True)
        from ui.widgets import IconRenderer

        self._icon_renderer = IconRenderer()
        self.tray = QSystemTrayIcon(self._icon_renderer.render())
        self.tray.setToolTip("Paragraphos")
        self.tray.activated.connect(self._on_tray_activated)

        self._rebuild_tray_menu(running=False)
        self.tray.show()

        # Re-render the tray icon when macOS flips light/dark so its
        # glyph color tracks the new menu-bar appearance.
        from ui.themes import manager as _theme_manager

        _tm = _theme_manager()
        if _tm is not None:
            _tm.themeChanged.connect(self._on_theme_changed)
        print(
            f"paragraphos ready — tray visible={self.tray.isVisible()}, "
            f"system-tray-available={QSystemTrayIcon.isSystemTrayAvailable()}",
            flush=True,
        )

        # Open the window FIRST, then catch-up, so the Stop button is wired
        # via ShowsTab.start_check() instead of running headless.
        QTimer.singleShot(300, self.open_window)

        self._window: MainWindow | None = None

        # Scheduler — runs in the APScheduler BackgroundScheduler (thread).
        # The cron job calls _run_check; Qt signals marshal back to the GUI thread.
        from core.scheduler import build_scheduler

        self._sched = build_scheduler(
            self.ctx.settings.daily_check_time, self._run_check_on_gui_thread
        )
        self._sched.start()

        if self.ctx.settings.catch_up_missed and should_catch_up(
            self.ctx.state.get_meta("last_successful_check"),
            self.ctx.settings.daily_check_time,
        ):
            # Fire AFTER the window opens (300ms) so ShowsTab owns the thread.
            QTimer.singleShot(2500, self._run_check)

    def _rebuild_tray_menu(
        self,
        *,
        running: bool,
        done: int = 0,
        total: int = 0,
        current_title: str = "",
        eta_sec: int | None = None,
    ) -> None:
        """Rebuild the tray context menu, swapping between idle and a
        rich status block while a queue run is active. Keeps a strong
        reference on `self` so the QMenu is not GC'd while shown."""
        from ui.menu_bar import build_tray_menu

        self._tray_menu = build_tray_menu(
            running=running,
            done=done,
            total=total,
            current_title=current_title,
            eta_sec=eta_sec,
            on_open=self.open_window,
            on_check_now=lambda: self._run_check(force=True),
            on_import_opml=self._import_opml,
            on_quit=self.quit_with_confirm,
        )
        self.tray.setContextMenu(self._tray_menu)

    def _on_update_available(self, tag: str, url: str) -> None:
        """GUI-thread receiver for the updater's async callback. Stores
        the (tag, url) on AppContext so any later-opened MainWindow can
        still find it, surfaces an in-window banner with a Download button,
        and fires a one-shot tray notification."""
        self.ctx.update_available_tag = tag
        self.ctx.update_available_url = url
        if self._window is not None:
            self._window.show_update_banner(tag, url)
        self.tray.showMessage(
            "Paragraphos update available",
            f"{tag} is out — you have v{_LOCAL_VERSION}. Click the Download button in the window.",
        )

    def _on_theme_changed(self, _mode: str) -> None:
        """Re-render the tray icon so its glyph color flips with the
        menu-bar appearance. Cheap — just re-draws a 22/44 px pixmap.
        Preserves the current idle vs. running state if any.
        """
        q = self.ctx.queue
        if q.running and q.total > 0:
            self.tray.setIcon(self._icon_renderer.render(q.done, q.total, running=True))
        else:
            self.tray.setIcon(self._icon_renderer.render())

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
            # If an update was detected before the window existed, surface
            # the banner now that there's a window to show it in.
            if self.ctx.update_available_tag and self.ctx.update_available_url:
                self._window.show_update_banner(
                    self.ctx.update_available_tag, self.ctx.update_available_url
                )
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _run_check_on_gui_thread(self) -> None:
        # Scheduled fire (APScheduler cron) — keep force=False so parked
        # feeds stay parked until their 1/3/7-day backoff window expires.
        QTimer.singleShot(0, self._run_check)

    def _run_check(self, *, force: bool = False) -> None:
        # If the window exists, delegate to ShowsTab.start_check() — that path
        # wires the Stop button correctly. Otherwise fall back to owning the
        # thread ourselves (e.g. a scheduler firing before the user opens the
        # window).
        #
        # ``force`` only propagates meaningfully to user-initiated entry
        # points (tray "Check now"). Scheduler / startup catch-up call this
        # with the default False so feed backoff is respected.
        if self._window is not None:
            started = self._window.shows_tab.start_check(force=force)
            if not started:
                self.tray.showMessage("Paragraphos", "A check is already running.")
                return
            self._thread = self._window.shows_tab._thread
        else:
            if self._thread and self._thread.isRunning():
                self.tray.showMessage("Paragraphos", "A check is already running.")
                return
            self._thread = CheckAllThread(self.ctx, self.ctx.settings, force=force)
            self._thread.start()
        # Whatever the source, connect app-level notification hooks.
        self._thread.episode_done.connect(self._on_episode_done)
        self._thread.finished_all.connect(self._on_check_done)

    def _on_episode_done(
        self,
        slug: str,
        guid: str,
        action: str,
        done_idx: int,
        total: int,
        show_title: str,
        ep_title: str,
    ) -> None:
        # Live tray icon — renders current fraction while a run is active.
        self.tray.setIcon(self._icon_renderer.render(done_idx, total, running=True))
        # Rich status block in the tray context menu — rebuilt on every
        # episode_done tick so the fraction / ETA / Now line stay live.
        q = self.ctx.queue
        eta = int(q.effective_avg_sec * (total - done_idx)) if q.effective_avg_sec else None
        self._rebuild_tray_menu(
            running=True,
            done=done_idx,
            total=total,
            current_title=f"{show_title} — {ep_title}",
            eta_sec=eta,
        )
        # Tally into the rolling run-summary — used by daily_summary mode.
        self._run_tally.setdefault(action, 0)
        self._run_tally[action] += 1
        if self._run_tally.get("_first_ep_title") is None and action == "transcribed":
            self._run_tally["_first_ep_title"] = f"{show_title} — {ep_title}"

        mode = self.ctx.settings.notify_mode
        if mode == "off":
            return
        if action != "transcribed":
            return
        spot_key = f"spotcheck_done:{slug}"
        title_prefix = f"{done_idx}/{total}"
        if self.ctx.state.get_meta(spot_key) != "1":
            # Spot-check: one-time per-show QA handshake. Respects
            # notify_mode="off" via the early-return above — users who
            # opted out of notifications get zero tray messages, ever.
            self.ctx.state.set_meta(spot_key, "1")
            self.tray.showMessage(
                f"✅ First transcript — {show_title}",
                f"{title_prefix} — {ep_title[:80]}\n"
                f"Open in Obsidian to spot-check the whisper_prompt quality.",
            )
            return
        if mode == "per_episode":
            self.tray.showMessage(
                f"{title_prefix} — {show_title}",
                ep_title[:120],
            )

    def quit_with_confirm(self) -> bool:
        """Show a confirm dialog if the queue is running / work would be lost.

        Returns True if the app is actually quitting, False if the user
        cancelled. Covers tray menu 'Quit' and Cmd+Q (via event filter).
        """
        if self._is_queue_busy():
            from PyQt6.QtWidgets import QMessageBox

            q = self.ctx.queue
            box = QMessageBox(
                QMessageBox.Icon.Warning,
                "Queue still running",
                f"Paragraphos is still working on {q.done}/{q.total} episodes. "
                "Quitting now will interrupt the current download/transcription "
                "— the partial MP3 survives (resumable), but a partial transcript "
                "will be discarded and re-run next time.\n\n"
                "Quit anyway?",
                QMessageBox.StandardButton.NoButton,
                self._window if self._window else None,
            )
            quit_btn = box.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Stay", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(box.buttons()[-1])  # Stay is safer default
            box.exec()
            if box.clickedButton() is not quit_btn:
                return False
        QApplication.quit()
        return True

    def _is_queue_busy(self) -> bool:
        q = self.ctx.queue
        if q.running:
            return True
        # Check the DB too — an episode might be mid-download/transcribe even
        # when q.running is False (e.g. app somehow lost thread state).
        with self.ctx.state._conn() as c:
            row = c.execute(
                "SELECT COUNT(*) FROM episodes WHERE status IN ('downloading','transcribing')"
            ).fetchone()
        return (row[0] or 0) > 0

    def _on_check_done(self) -> None:
        self.ctx.state.set_meta(
            "last_successful_check",
            datetime.now(timezone.utc).isoformat(),
        )
        # Daily-summary notification: single consolidated message after a
        # run instead of one-per-episode. Useful for overnight catch-ups.
        if self.ctx.settings.notify_mode == "daily_summary":
            t = self._run_tally
            done = int(t.get("transcribed", 0))
            skipped = int(t.get("skipped", 0))
            failed = int(t.get("failed", 0))
            if done + failed > 0:
                parts = []
                if done:
                    parts.append(f"{done} new")
                if failed:
                    parts.append(f"{failed} failed")
                if skipped:
                    parts.append(f"{skipped} skipped")
                self.tray.showMessage(
                    "Paragraphos — run complete",
                    " · ".join(parts) + "\n" + f"First: {t.get('_first_ep_title') or '—'}",
                )
        self._run_tally = {}
        # Revert tray context menu to the idle shape.
        self._rebuild_tray_menu(running=False)
        # Briefly show ✓ on the tray, then revert to idle 'P'.
        self.tray.setIcon(self._icon_renderer.render(override_text="✓"))
        QTimer.singleShot(5000, lambda: self.tray.setIcon(self._icon_renderer.render()))
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
            self.tray.showMessage("OPML import failed", str(e))
            return
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
            self.ctx.watchlist.shows.append(
                Show(
                    slug=slug,
                    title=meta["title"] or entry["title"],
                    rss=entry["xmlUrl"],
                    whisper_prompt="",
                )
            )
            for ep in manifest:
                self.ctx.state.upsert_episode(
                    show_slug=slug,
                    guid=ep["guid"],
                    title=ep["title"],
                    pub_date=ep["pubDate"],
                    mp3_url=ep["mp3_url"],
                )
            added += 1
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        self.tray.showMessage("OPML imported", f"Added {added} show(s) from {path.name}")
        if self._window:
            self._window.shows_tab.refresh()

    def _import_opml(self) -> None:
        from core.models import Show
        from core.opml import parse_opml
        from core.rss import build_manifest, feed_metadata

        path, _filter = QFileDialog.getOpenFileName(
            None, "Select OPML file", str(Path.home()), "OPML (*.opml *.xml)"
        )
        if not path:
            return
        try:
            entries = parse_opml(Path(path))
        except Exception as e:
            QMessageBox.warning(None, "OPML error", str(e))
            return

        existing = {s.slug for s in self.ctx.watchlist.shows}
        added, errors = 0, []
        for entry in entries:
            try:
                meta = feed_metadata(entry["xmlUrl"])
                manifest = build_manifest(entry["xmlUrl"], timeout=60)
            except Exception as e:
                errors.append(f"{entry['title']}: {e}")
                continue
            slug = (meta["title"] or entry["title"]).lower().replace(" ", "-")
            if slug in existing:
                continue
            self.ctx.watchlist.shows.append(
                Show(
                    slug=slug,
                    title=meta["title"] or entry["title"],
                    rss=entry["xmlUrl"],
                    whisper_prompt="",
                )
            )
            for ep in manifest:
                self.ctx.state.upsert_episode(
                    show_slug=slug,
                    guid=ep["guid"],
                    title=ep["title"],
                    pub_date=ep["pubDate"],
                    mp3_url=ep["mp3_url"],
                )
            added += 1
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        summary = f"Imported {added} new show(s)."
        if errors:
            summary += "\n\nErrors (first 10):\n" + "\n".join(errors[:10])
        QMessageBox.information(None, "OPML import", summary)


class ParagraphosQApplication(QApplication):
    """Intercepts macOS QFileOpenEvent so Finder → Dock drops of .opml files
    land inside the running app instead of launching a new instance.

    Also intercepts QuitEvent (⌘Q, app menu Quit) to route it through our
    confirm-if-queue-running dialog. A weak reference to ParagraphosApp is set
    from main() so we can delegate.
    """

    file_opened = pyqtSignal(str)
    quit_requested = pyqtSignal()

    def event(self, e):
        t = e.type()
        if t == QEvent.Type.FileOpen and isinstance(e, QFileOpenEvent):
            self.file_opened.emit(e.file())
            return True
        if t == QEvent.Type.Quit:
            # Delegate to the app-owned handler. Quit-events arrive from
            # Cmd+Q, Dock → Quit, and apple-quit — catch them all.
            self.quit_requested.emit()
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

    # App / dock / window icon — bundled AppIcon.icns.
    _icon_path = Path(__file__).resolve().parent / "assets" / "AppIcon.icns"
    if _icon_path.exists():
        qapp.setWindowIcon(QIcon(str(_icon_path)))

    # Install the theme manager BEFORE any widget construction — widgets
    # subscribe to its themeChanged signal at __init__ time.
    from ui.themes import install_manager

    install_manager(qapp)
    _focus_filter = _FocusClearFilter()
    qapp.installEventFilter(_focus_filter)
    qapp._focus_filter = _focus_filter  # keep reference alive
    if not show_wizard_if_needed(qapp):
        print("First-run wizard cancelled — exiting.", flush=True)
        return 0
    app = ParagraphosApp()
    qapp.file_opened.connect(app.on_file_dropped)
    qapp.quit_requested.connect(app.quit_with_confirm)
    from core.http import close_client

    qapp.aboutToQuit.connect(close_client)
    ParagraphosApp.instance = app  # keep reference
    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
