"""Main window: sidebar nav + stacked pages + log dock + wiki-compile banner."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDateTime, QLocale, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from core.paths import user_data_dir  # noqa: E402
from ui.about_dialog import AboutPane
from ui.app_context import AppContext
from ui.failed_tab import FailedTab
from ui.log_dock import LogDock, LogsPane
from ui.menu_bar import build_menu_bar
from ui.queue_tab import QueueTab
from ui.settings_pane import SettingsPane
from ui.shows_tab import ShowsTab
from ui.widgets import Sidebar

DATA_DIR = user_data_dir()


def _fmt_elapsed(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def _fmt_dt_locale(dt) -> str:
    """Format datetime as 'ddd, <locale-short-date> HH:MM'.

    Respects the macOS system locale — DE users see '21.04.2026', US users
    see '4/21/26'. 'ddd' is localized too (Mo/Mon/etc.).
    """
    qdt = QDateTime.fromSecsSinceEpoch(int(dt.timestamp()))
    loc = QLocale.system()
    date_fmt = loc.dateFormat(QLocale.FormatType.ShortFormat)
    # Prefer 4-digit year for readability; Qt short-format on macOS DE already
    # uses 'dd.MM.yyyy' so this is usually a no-op.
    if "yyyy" not in date_fmt:
        date_fmt = date_fmt.replace("yy", "yyyy")
    return loc.toString(qdt, f"ddd, {date_fmt} HH:mm")


def _last_compiled_path(ctx) -> Path:
    """Path to the knowledge-hub's compile marker, driven by settings so the
    banner works after Paragraphos is extracted into its own repo."""
    root = Path(ctx.settings.knowledge_hub_root).expanduser()
    return root / "raw" / ".last_compiled"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Paragraphos")
        self.ctx = AppContext.load(DATA_DIR)

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        self.banner = QLabel()
        self._apply_banner_style()
        self.banner.setVisible(False)
        outer.addWidget(self.banner)

        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar()
        self.sidebar.add_group("Library")
        for key, label in (("shows", "Shows"), ("queue", "Queue"), ("failed", "Failed")):
            self.sidebar.add_item(key, label)
        self.sidebar.add_group("System")
        for key, label in (("settings", "Settings"), ("logs", "Logs"), ("about", "About")):
            self.sidebar.add_item(key, label)
        self.sidebar.finish()
        self.sidebar.set_active("shows")
        self.sidebar.navigate.connect(self._on_nav)
        root.addWidget(self.sidebar)

        # Stacked pages on the right
        self.stack = QStackedWidget()
        self.shows_tab = ShowsTab(self.ctx)
        self.queue_tab = QueueTab(self.ctx)
        self.failed_tab = FailedTab(self.ctx)
        self.settings_pane = SettingsPane(self.ctx)
        self.logs_pane = LogsPane(self)
        self.about_pane = AboutPane(self)
        # Let ShowsTab forward queue signals to the queue tab.
        self.shows_tab.queue_listener = self.queue_tab  # type: ignore[attr-defined]
        for w in (
            self.shows_tab,
            self.queue_tab,
            self.failed_tab,
            self.settings_pane,
            self.logs_pane,
            self.about_pane,
        ):
            self.stack.addWidget(w)
        self._nav_index = {
            "shows": 0,
            "queue": 1,
            "failed": 2,
            "settings": 3,
            "logs": 4,
            "about": 5,
        }
        root.addWidget(self.stack, stretch=1)

        outer.addWidget(body, stretch=1)
        self.setCentralWidget(central)

        self.log_dock = LogDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)

        # Fan every log message into both the dock (bottom) and the
        # sidebar Logs pane so they stay in sync.
        def _log_sink(msg: str) -> None:
            self.log_dock.append(msg)
            self.logs_pane.append(msg)

        self.shows_tab.log_sink = _log_sink  # type: ignore[attr-defined]

        self.setMenuBar(build_menu_bar(self))

        # Window-scoped shortcuts (menu items also register these, but explicit
        # QShortcuts guarantee they work even when no menu-item is focused).
        for key, fn in (
            (QKeySequence.StandardKey.Preferences, lambda: self._on_nav("settings")),
            ("Ctrl+R", self.shows_tab.start_check),
            ("Ctrl+.", self.shows_tab._stop),
            ("Ctrl+L", lambda: self.log_dock.setVisible(not self.log_dock.isVisible())),
            ("?", lambda: self._show_cheatsheet()),
            ("Ctrl+/", lambda: self._show_cheatsheet()),
        ):
            QShortcut(
                QKeySequence(key) if isinstance(key, str) else QKeySequence(key), self, activated=fn
            )

        # Global status bar — visible from every tab.
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        sb.addPermanentWidget(self.status_label, stretch=1)
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status_bar)
        self._status_timer.start(1000)
        self._refresh_status_bar()

        self._refresh_banner()
        self.resize(1100, 720)

        # Sidebar counts: once at startup, then periodically so they stay
        # fresh after checks finish, retries, etc.
        self._update_sidebar_counts()
        self._counts_timer = QTimer(self)
        self._counts_timer.timeout.connect(self._update_sidebar_counts)
        self._counts_timer.start(2000)

    def _apply_banner_style(self) -> None:
        """Choose banner colors that work in both light and dark macOS modes."""
        palette_color = self.palette().window().color()
        lightness = palette_color.lightnessF()
        if lightness < 0.5:
            # Dark mode: dark amber bg, soft cream text, subtle border
            self.banner.setStyleSheet(
                "background:#4a3f00; color:#ffe7a0; padding:8px 12px; "
                "border:1px solid #8a6b00; border-radius:4px;"
            )
        else:
            self.banner.setStyleSheet(
                "background:#fff7d0; color:#3a2d00; padding:8px 12px; "
                "border:1px solid #e0c870; border-radius:4px;"
            )

    def _on_nav(self, key: str) -> None:
        idx = self._nav_index.get(key)
        if idx is not None:
            self.stack.setCurrentIndex(idx)
            self.sidebar.set_active(key)
            w = self.stack.widget(idx)
            if hasattr(w, "refresh"):
                w.refresh()
            self._refresh_banner()

    def _show_cheatsheet(self) -> None:
        # Toggle: re-pressing the trigger while the dialog is open closes it
        # (handled in the dialog's keyPressEvent for `?`; for Cmd+/ we just
        # re-open which raises the existing instance).
        existing = getattr(self, "_cheatsheet_dlg", None)
        if existing is not None and existing.isVisible():
            existing.close()
            return
        from ui.shortcut_cheatsheet import ShortcutCheatsheet

        self._cheatsheet_dlg = ShortcutCheatsheet(self)
        self._cheatsheet_dlg.show()
        self._cheatsheet_dlg.raise_()
        self._cheatsheet_dlg.activateWindow()

    def _update_sidebar_counts(self) -> None:
        try:
            with self.ctx.state._conn() as c:
                pending = c.execute(
                    "SELECT COUNT(*) FROM episodes WHERE status='pending'"
                ).fetchone()[0]
                failed = c.execute(
                    "SELECT COUNT(*) FROM episodes WHERE status='failed'"
                ).fetchone()[0]
        except Exception:
            pending = failed = 0
        self.sidebar.set_count("shows", len(self.ctx.watchlist.shows))
        self.sidebar.set_count("queue", pending)
        self.sidebar.set_count("failed", failed)

    def _refresh_status_bar(self) -> None:
        from datetime import datetime, timedelta

        q = self.ctx.queue
        if not q.running:
            paused = self.ctx.state.get_meta("queue_paused") == "1"
            if paused:
                self.status_label.setText(
                    "<span style='color:#a06030;'>● queue paused</span> "
                    "— click Start on any tab to resume"
                )
            else:
                self.status_label.setText("<span style='color:#888;'>● idle</span>")
            return
        elapsed = (datetime.now() - q.started_at).total_seconds() if q.started_at else 0
        remaining = q.total - q.done
        avg = q.effective_avg_sec
        eta_sec = avg * remaining if avg else 0
        finish_at = datetime.now() + timedelta(seconds=eta_sec) if eta_sec else None
        parts = [
            "<span style='color:#4a7aa0;'>● running</span>",
            f"<b>{q.done}/{q.total}</b>",
        ]
        if q.started_at:
            parts.append(f"started {_fmt_dt_locale(q.started_at)}")
            parts.append(f"elapsed {_fmt_elapsed(elapsed)}")
        if avg:
            # Mark fallback estimates so the user knows "finish ≈" is based
            # on historical averages when no live episode has finished yet.
            tag = "ETA" if q.avg_sec_per_episode else "ETA (est.)"
            parts.append(f"{tag} {_fmt_elapsed(eta_sec)}")
            if finish_at:
                parts.append(f"finish ≈ {_fmt_dt_locale(finish_at)}")
        self.status_label.setText(" · ".join(parts))

    def _refresh_banner(self) -> None:
        output_root = Path(self.ctx.settings.output_root).expanduser()
        if not output_root.exists():
            self.banner.setVisible(False)
            return
        last_compiled_mtime = 0.0
        lc = _last_compiled_path(self.ctx)
        if lc.exists():
            last_compiled_mtime = lc.stat().st_mtime
        new_count = 0
        for md in output_root.rglob("*.md"):
            if md.name == "index.md":
                continue
            if md.stat().st_mtime > last_compiled_mtime:
                new_count += 1
        if new_count > 0:
            self.banner.setText(
                f"📝 {new_count} transcripts newer than last wiki compile "
                f"— run the 'Compile' workflow in Claude to pull them into the wiki."
            )
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)
