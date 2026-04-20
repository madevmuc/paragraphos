"""Add Podcast dialog — search iTunes / parse URL, preview, save."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QDialog, QFormLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QTextEdit, QVBoxLayout)

from core.discovery import find_rss_from_url, search_itunes
from core.models import Show
from core.prompt_gen import suggest_whisper_prompt
from core.rss import build_manifest, feed_metadata
from core.state import EpisodeStatus


class AddShowDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.updated_watchlist = ctx.watchlist
        self.setWindowTitle("Add Podcast")
        self.resize(750, 600)

        v = QVBoxLayout(self)
        v.addWidget(QLabel("Name or URL:"))
        self.input = QLineEdit()
        self.input.returnPressed.connect(self._search)
        v.addWidget(self.input)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._search)
        v.addWidget(search_btn)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self._pick)
        v.addWidget(self.results)

        form = QFormLayout()
        self.slug = QLineEdit()
        self.title = QLineEdit()
        self.rss = QLineEdit()
        self.prompt = QTextEdit()
        self.backlog = QComboBox()
        self.backlog.addItems(["All episodes", "Only new from now", "Last 20", "Last 50"])
        form.addRow("Slug", self.slug)
        form.addRow("Title", self.title)
        form.addRow("RSS", self.rss)
        form.addRow("Whisper prompt", self.prompt)
        form.addRow("Backlog", self.backlog)
        v.addLayout(form)

        save = QPushButton("Save")
        save.clicked.connect(self._save)
        v.addWidget(save)

    def _search(self):
        term = self.input.text().strip()
        if not term: return
        self.results.clear()
        try:
            if term.startswith("http"):
                rss = find_rss_from_url(term)
                if rss:
                    self._fill_from_feed(rss)
                    return
                QMessageBox.warning(self, "Not found", "No RSS link on that page.")
                return
            for m in search_itunes(term):
                item = QListWidgetItem(f"{m.title} — {m.author}")
                item.setData(Qt.ItemDataRole.UserRole, m.feed_url)
                self.results.addItem(item)
            if self.results.count() == 0:
                QMessageBox.information(self, "No matches", "iTunes returned no results.")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _pick(self, item: QListWidgetItem):
        self._fill_from_feed(item.data(Qt.ItemDataRole.UserRole))

    def _fill_from_feed(self, rss: str):
        try:
            meta = feed_metadata(rss)
            manifest = build_manifest(rss)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self.rss.setText(rss)
        self.title.setText(meta["title"])
        default_slug = (meta["title"] or "show").lower().replace(" ", "-")
        self.slug.setText(default_slug)
        prompt = suggest_whisper_prompt(
            title=meta["title"], author=meta["author"],
            episodes=[{"title": e["title"], "description": e["description"]}
                      for e in manifest[-20:]],
        )
        self.prompt.setPlainText(prompt)
        self._loaded_manifest = manifest

    def _save(self):
        slug = self.slug.text().strip()
        if not slug:
            QMessageBox.warning(self, "Missing", "Slug required.")
            return
        if any(s.slug == slug for s in self.updated_watchlist.shows):
            QMessageBox.warning(self, "Exists", f"{slug!r} is already in the watchlist.")
            return
        show = Show(
            slug=slug, title=self.title.text().strip(),
            rss=self.rss.text().strip(),
            whisper_prompt=self.prompt.toPlainText().strip(),
        )
        self.updated_watchlist.shows.append(show)
        self.updated_watchlist.save(self.ctx.data_dir / "watchlist.yaml")

        # Seed episodes in state; handle backlog strategy.
        manifest = getattr(self, "_loaded_manifest", [])
        mode = self.backlog.currentText()
        for ep in manifest:
            self.ctx.state.upsert_episode(
                show_slug=slug, guid=ep["guid"], title=ep["title"],
                pub_date=ep["pubDate"], mp3_url=ep["mp3_url"])

        if mode == "Only new from now":
            # Mark all existing episodes done so only future ones will be picked up.
            with self.ctx.state._conn() as c:
                c.execute("UPDATE episodes SET status='done' "
                          "WHERE show_slug=? AND status='pending'", (slug,))
        elif mode.startswith("Last "):
            n = int(mode.split()[1])
            with self.ctx.state._conn() as c:
                c.execute("""
                    UPDATE episodes SET status='done'
                    WHERE show_slug=? AND guid NOT IN (
                        SELECT guid FROM episodes WHERE show_slug=?
                        ORDER BY pub_date DESC LIMIT ?
                    )""", (slug, slug, n))
        # "All episodes" leaves everything pending.

        self.accept()
