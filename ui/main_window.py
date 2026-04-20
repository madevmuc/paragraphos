"""Main window: tabs (Shows/Failed/Settings) + log dock + wiki-compile banner."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDateTime, QLocale, Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QLabel, QMainWindow, QStatusBar, QTabWidget, QVBoxLayout, QWidget

from ui.app_context import AppContext
from ui.failed_tab import FailedTab
from ui.log_dock import LogDock
from ui.menu_bar import build_menu_bar
from ui.queue_tab import QueueTab
from ui.settings_pane import SettingsPane
from ui.shows_tab import ShowsTab

from core.paths import user_data_dir  # noqa: E402
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
REPO_ROOT = Path(__file__).resolve().parents[3]
LAST_COMPILED = REPO_ROOT / "raw" / ".last_compiled"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Paragraphos")
        self.ctx = AppContext.load(DATA_DIR)

        central = QWidget()
        layout = QVBoxLayout(central)
        self.banner = QLabel()
        self._apply_banner_style()
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

        self.tabs = QTabWidget()
        self.shows_tab = ShowsTab(self.ctx)
        self.queue_tab = QueueTab(self.ctx)
        self.failed_tab = FailedTab(self.ctx)
        self.settings_pane = SettingsPane(self.ctx)
        self.tabs.addTab(self.shows_tab, "Shows")
        self.tabs.addTab(self.queue_tab, "Queue")
        self.tabs.addTab(self.failed_tab, "Failed")
        self.tabs.addTab(self.settings_pane, "Settings")
        # Let ShowsTab forward queue signals to the queue tab.
        self.shows_tab.queue_listener = self.queue_tab  # type: ignore[attr-defined]
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.log_dock = LogDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.shows_tab.log_sink = self.log_dock.append  # type: ignore[attr-defined]

        self.setMenuBar(build_menu_bar(self))

        # Window-scoped shortcuts (menu items also register these, but explicit
        # QShortcuts guarantee they work even when no menu-item is focused).
        for key, fn in (
            (QKeySequence.StandardKey.Preferences, lambda: self.tabs.setCurrentIndex(3)),
            ("Ctrl+R", self.shows_tab.start_check),
            ("Ctrl+.", self.shows_tab._stop),
            ("Ctrl+L", lambda: self.log_dock.setVisible(not self.log_dock.isVisible())),
        ):
            QShortcut(QKeySequence(key) if isinstance(key, str) else QKeySequence(key),
                      self, activated=fn)

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

    def _apply_banner_style(self) -> None:
        """Choose banner colors that work in both light and dark macOS modes."""
        palette_color = self.palette().window().color()
        lightness = palette_color.lightnessF()
        if lightness < 0.5:
            # Dark mode: dark amber bg, soft cream text, subtle border
            self.banner.setStyleSheet(
                "background:#4a3f00; color:#ffe7a0; padding:8px 12px; "
                "border:1px solid #8a6b00; border-radius:4px;")
        else:
            self.banner.setStyleSheet(
                "background:#fff7d0; color:#3a2d00; padding:8px 12px; "
                "border:1px solid #e0c870; border-radius:4px;")

    def _on_tab_changed(self, idx: int) -> None:
        w = self.tabs.widget(idx)
        if hasattr(w, "refresh"):
            w.refresh()
        self._refresh_banner()

    def _refresh_status_bar(self) -> None:
        from datetime import datetime, timedelta
        q = self.ctx.queue
        if not q.running:
            paused = self.ctx.state.get_meta("queue_paused") == "1"
            if paused:
                self.status_label.setText(
                    "<span style='color:#a06030;'>● queue paused</span> "
                    "— click Start on any tab to resume")
            else:
                self.status_label.setText(
                    "<span style='color:#888;'>● idle</span>")
            return
        elapsed = (datetime.now() - q.started_at).total_seconds() if q.started_at else 0
        remaining = q.total - q.done
        avg = q.effective_avg_sec
        eta_sec = avg * remaining if avg else 0
        finish_at = (datetime.now() + timedelta(seconds=eta_sec)
                     if eta_sec else None)
        parts = [
            f"<span style='color:#4a7aa0;'>● running</span>",
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
        if LAST_COMPILED.exists():
            last_compiled_mtime = LAST_COMPILED.stat().st_mtime
        new_count = 0
        for md in output_root.rglob("*.md"):
            if md.name == "index.md":
                continue
            if md.stat().st_mtime > last_compiled_mtime:
                new_count += 1
        if new_count > 0:
            self.banner.setText(
                f"📝 {new_count} transcripts newer than last wiki compile "
                f"— run the 'Compile' workflow in Claude to pull them into the wiki.")
            self.banner.setVisible(True)
        else:
            self.banner.setVisible(False)
