"""Add Episodes dialog — curated list of individual URLs."""

from __future__ import annotations

from PyQt6.QtWidgets import (QComboBox, QDialog, QLabel, QMessageBox,
                             QPushButton, QTextEdit, QVBoxLayout)

from core.sanitize import sanitize_filename
from core.scrape import scrape_episode


class AddEpisodesDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Add Episodes")
        self.resize(650, 450)

        v = QVBoxLayout(self)
        v.addWidget(QLabel("Paste URLs (one per line) — MP3 direct or episode landing page:"))
        self.urls = QTextEdit()
        v.addWidget(self.urls)
        v.addWidget(QLabel("Assign to show:"))
        self.show_picker = QComboBox()
        self.show_picker.addItems([s.slug for s in ctx.watchlist.shows])
        self.show_picker.addItem("<detect-from-scrape>")
        v.addWidget(self.show_picker)
        go = QPushButton("Queue")
        go.clicked.connect(self._queue)
        v.addWidget(go)

    def _queue(self):
        urls = [u.strip() for u in self.urls.toPlainText().splitlines() if u.strip()]
        target_slug = self.show_picker.currentText()
        added, skipped, errors = 0, 0, []
        for u in urls:
            try:
                ep = scrape_episode(u)
            except Exception as e:
                errors.append(f"{u}: {e}")
                continue
            slug_for_show = target_slug
            if slug_for_show.startswith("<detect"):
                slug_for_show = sanitize_filename(
                    (ep.show_name or "curated").lower()).replace(" ", "-")
            guid = ep.source_url or ep.mp3_url
            existing = self.ctx.state.get_episode(guid)
            if existing:
                skipped += 1
                continue
            self.ctx.state.upsert_episode(
                show_slug=slug_for_show, guid=guid, title=ep.title,
                pub_date=ep.pub_date or "1970-01-01", mp3_url=ep.mp3_url,
            )
            added += 1
        msg = f"Queued: {added}, skipped (dup): {skipped}"
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors[:10])
        QMessageBox.information(self, "Done", msg)
        self.accept()
