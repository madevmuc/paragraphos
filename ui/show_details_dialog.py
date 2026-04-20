"""Per-show details dialog — opens on row-double-click in Shows tab.

Shows: stats, RSS URL, language picker, whisper_prompt editor, recent
episodes with status + attempt history.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                             QHeaderView, QLabel, QLineEdit, QPlainTextEdit,
                             QPushButton, QTableWidget, QTableWidgetItem,
                             QTabWidget, QVBoxLayout, QWidget)

from core.stats import compute_show_stats, format_duration

LANGUAGES = [
    ("Deutsch", "de"), ("English", "en"), ("Español", "es"),
    ("Français", "fr"), ("Italiano", "it"), ("Nederlands", "nl"),
    ("Português", "pt"), ("Polski", "pl"), ("Čeština", "cs"),
    ("Русский", "ru"), ("日本語", "ja"), ("中文", "zh"),
    ("Auto-detect", "auto"),
]


class ShowDetailsDialog(QDialog):
    def __init__(self, ctx, slug: str, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.slug = slug
        self.show_ = next((s for s in ctx.watchlist.shows if s.slug == slug), None)
        if self.show_ is None:
            self.reject(); return
        self.setWindowTitle(f"{self.show_.title}  —  {slug}")
        self.resize(820, 620)

        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._stats_tab(), "Overview")
        tabs.addTab(self._settings_tab(), "Settings")
        tabs.addTab(self._episodes_tab(), "Episodes")
        root.addWidget(tabs)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save); bb.rejected.connect(self.reject)
        root.addWidget(bb)

    # ── tabs ─────────────────────────────────────────────────

    def _stats_tab(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        s = compute_show_stats(self.ctx.state, self.slug)
        f.addRow("Total episodes", QLabel(str(s.total)))
        f.addRow("Transcribed", QLabel(f"{s.done}  ({s.done * 100 // max(s.total,1)}%)"))
        f.addRow("Pending", QLabel(str(s.pending)))
        f.addRow("Failed", QLabel(str(s.failed)))
        f.addRow("Total duration", QLabel(format_duration(s.total_seconds)))
        f.addRow("Total words", QLabel(f"{s.total_words:,}".replace(",", ".")))
        if s.done:
            f.addRow("Avg duration/ep", QLabel(format_duration(s.avg_duration_sec)))
            f.addRow("Avg words/ep", QLabel(f"{s.avg_words:,}".replace(",", ".")))
        f.addRow("Last completed", QLabel(s.last_completed or "—"))
        f.addRow("RSS URL", QLabel(f"<a href='{self.show_.rss}'>{self.show_.rss}</a>"))
        return w

    def _settings_tab(self) -> QWidget:
        w = QWidget(); f = QFormLayout(w)
        self.slug_edit = QLineEdit(self.show_.slug); self.slug_edit.setEnabled(False)
        f.addRow("Slug", self.slug_edit)
        self.title_edit = QLineEdit(self.show_.title)
        f.addRow("Title", self.title_edit)
        self.rss_edit = QLineEdit(self.show_.rss)
        f.addRow("RSS URL", self.rss_edit)

        self.language = QComboBox()
        for label, code in LANGUAGES:
            self.language.addItem(f"{label} ({code})", code)
        # Select current
        current = self.show_.language
        idx = next((i for i, (_, c) in enumerate(LANGUAGES) if c == current), 0)
        self.language.setCurrentIndex(idx)
        f.addRow("Whisper language", self.language)

        self.prompt_edit = QPlainTextEdit(self.show_.whisper_prompt)
        self.prompt_edit.setPlaceholderText(
            "Host names + domain jargon — highest-leverage quality knob.")
        f.addRow("Whisper prompt", self.prompt_edit)

        return w

    def _episodes_tab(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w)
        tbl = QTableWidget(0, 5)
        tbl.setHorizontalHeaderLabels(["Pub Date", "Title", "Status", "Words", "Duration"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        v.addWidget(tbl)
        with self.ctx.state._conn() as c:
            rows = c.execute(
                "SELECT pub_date, title, status, word_count, duration_sec "
                "FROM episodes WHERE show_slug=? ORDER BY pub_date DESC",
                (self.slug,)).fetchall()
        tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            tbl.setItem(i, 0, QTableWidgetItem(r["pub_date"] or ""))
            tbl.setItem(i, 1, QTableWidgetItem(r["title"] or ""))
            tbl.setItem(i, 2, QTableWidgetItem(r["status"] or ""))
            tbl.setItem(i, 3, QTableWidgetItem(
                str(r["word_count"]) if r["word_count"] else ""))
            dur = r["duration_sec"]
            tbl.setItem(i, 4, QTableWidgetItem(
                format_duration(dur) if dur else ""))
        return w

    # ── save ─────────────────────────────────────────────────

    def _save(self):
        self.show_.title = self.title_edit.text().strip()
        self.show_.rss = self.rss_edit.text().strip()
        self.show_.language = self.language.currentData()
        self.show_.whisper_prompt = self.prompt_edit.toPlainText().strip()
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        self.accept()
