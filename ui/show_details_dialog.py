"""Per-show details dialog — opens on row-double-click in Shows tab.

Restyled for v1.0 ship: fixed 620×440 dialog with an artwork header, a
120 px / flex form grid, a last-10 recent-episodes table with status
`Pill`s, and a footer row (Remove · Mark stale · Save).

Save / remove / mark-stale logic is preserved from the previous revision
— only the layout and widget composition changed.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.stats import compute_show_stats
from ui.retranscribe import retranscribe_episode
from ui.widgets.pill import Pill

# Episode-status → Pill-kind mapping. `done` is the canonical success
# state in `core.stats`; other values map conservatively.
_STATUS_PILL_KIND = {
    "done": "ok",
    "transcribed": "ok",
    "failed": "fail",
    "pending": "running",
    "downloading": "running",
    "skipped": "idle",
}

# (display label, whisper language code) — mirrors the pre-restyle picker.
_LANGUAGES = [
    ("Deutsch", "de"),
    ("English", "en"),
    ("Español", "es"),
    ("Français", "fr"),
    ("Italiano", "it"),
    ("Nederlands", "nl"),
    ("Português", "pt"),
    ("Polski", "pl"),
    ("Čeština", "cs"),
    ("Русский", "ru"),
    ("日本語", "ja"),
    ("中文", "zh"),
    ("Auto-detect", "auto"),
]


class ShowDetailsDialog(QDialog):
    def __init__(self, ctx, slug: str, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.slug = slug
        self.show_ = next((s for s in ctx.watchlist.shows if s.slug == slug), None)
        if self.show_ is None:
            self.reject()
            return
        self.setWindowTitle(f"{self.show_.title} — Details")
        self.setFixedSize(620, 440)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        root.addLayout(self._build_header())
        root.addLayout(self._build_form())
        root.addWidget(self._build_advanced_group())
        root.addWidget(self._build_episodes_table(), 1)
        root.addLayout(self._build_footer())

    # ── header ───────────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        art = QLabel()
        art.setFixedSize(64, 64)
        art.setFrameShape(QFrame.Shape.StyledPanel)
        art.setStyleSheet(
            "QLabel { background: palette(alternate-base);"
            " border: 1px solid palette(mid); border-radius: 6px; }"
        )
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Show model has no artwork URL field in this repo; placeholder only.
        art.setText("🎙")
        art.setObjectName("ShowArtwork")
        row.addWidget(art, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title = QLabel(self.show_.title or self.show_.slug)
        f = QFont()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        title.setWordWrap(True)
        text_col.addWidget(title)

        s = compute_show_stats(self.ctx.state, self.slug)
        meta_text = f"{self.show_.slug} · {s.total} eps · " f"{s.done} done · {s.pending} pending"
        meta = QLabel(meta_text)
        meta.setProperty("class", "muted")
        meta.setStyleSheet("color: palette(mid); font-size: 11px;")
        text_col.addWidget(meta)

        feed = QLabel(self.show_.rss)
        feed.setStyleSheet("color: palette(mid); font-family: Menlo, monospace; font-size: 11px;")
        feed.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_col.addWidget(feed)
        text_col.addStretch(1)

        row.addLayout(text_col, 1)
        return row

    # ── form grid ────────────────────────────────────────────

    def _build_form(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 120)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        r = 0

        grid.addWidget(self._label("Slug"), r, 0)
        self.slug_edit = QLineEdit(self.show_.slug)
        self.slug_edit.setReadOnly(True)
        self.slug_edit.setEnabled(False)
        grid.addWidget(self.slug_edit, r, 1)
        r += 1

        grid.addWidget(self._label("Feed URL"), r, 0)
        self.rss_edit = QLineEdit(self.show_.rss)
        grid.addWidget(self.rss_edit, r, 1)
        r += 1

        grid.addWidget(self._label("Enabled"), r, 0)
        self.enabled_toggle = QCheckBox()
        self.enabled_toggle.setChecked(bool(self.show_.enabled))
        grid.addWidget(self.enabled_toggle, r, 1)
        r += 1

        grid.addWidget(self._label("Last checked"), r, 0)
        last_checked = self._fmt_last_checked()
        self.last_checked_lbl = QLabel(last_checked)
        self.last_checked_lbl.setStyleSheet("color: palette(mid);")
        grid.addWidget(self.last_checked_lbl, r, 1)
        r += 1

        grid.addWidget(self._label("Backlog"), r, 0)
        self.backlog_lbl = QLabel(self._fmt_backlog())
        self.backlog_lbl.setStyleSheet("color: palette(mid);")
        grid.addWidget(self.backlog_lbl, r, 1)
        r += 1

        grid.addWidget(self._label("Output subdir"), r, 0)
        self.output_edit = QLineEdit(self.show_.output_override or "")
        self.output_edit.setPlaceholderText(f"(default: {self.show_.slug})")
        grid.addWidget(self.output_edit, r, 1)
        r += 1

        return grid

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: palette(mid); font-size: 12px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return lbl

    def _fmt_last_checked(self) -> str:
        try:
            v = self.ctx.state.get_meta("last_successful_check")
        except Exception:
            v = None
        return v if v else "—"

    def _fmt_backlog(self) -> str:
        try:
            with self.ctx.state._conn() as c:
                row = c.execute(
                    "SELECT "
                    "SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending, "
                    "SUM(CASE WHEN status='failed'  THEN 1 ELSE 0 END) AS failed  "
                    "FROM episodes WHERE show_slug=?",
                    (self.slug,),
                ).fetchone()
            p = row["pending"] or 0
            fa = row["failed"] or 0
            return f"{p} pending · {fa} failed"
        except Exception:
            return "—"

    # ── advanced (collapsed by default) ──────────────────────

    def _build_advanced_group(self) -> QGroupBox:
        box = QGroupBox("Advanced — tuning")
        box.setCheckable(True)
        box.setChecked(False)  # collapsed by default
        box.setFlat(True)

        inner = QGridLayout(box)
        inner.setHorizontalSpacing(10)
        inner.setVerticalSpacing(6)
        inner.setColumnMinimumWidth(0, 120)
        inner.setColumnStretch(0, 0)
        inner.setColumnStretch(1, 1)

        r = 0
        inner.addWidget(self._label("Title"), r, 0)
        self._title_edit = QLineEdit(self.show_.title or "")
        inner.addWidget(self._title_edit, r, 1)
        r += 1

        inner.addWidget(self._label("Language"), r, 0)
        self._language_combo = QComboBox()
        for label, code in _LANGUAGES:
            self._language_combo.addItem(f"{label} ({code})", code)
        current = getattr(self.show_, "language", "de") or "de"
        idx = next((i for i, (_, c) in enumerate(_LANGUAGES) if c == current), 0)
        self._language_combo.setCurrentIndex(idx)
        inner.addWidget(self._language_combo, r, 1)
        r += 1

        inner.addWidget(self._label("Whisper prompt"), r, 0)
        self._whisper_prompt_edit = QPlainTextEdit(self.show_.whisper_prompt or "")
        self._whisper_prompt_edit.setFixedHeight(64)
        inner.addWidget(self._whisper_prompt_edit, r, 1)
        r += 1

        hint = QLabel("Comma-separated hints (names, jargon, places). " "Improves recognition.")
        hint.setStyleSheet("color: palette(mid); font-size: 11px;")
        hint.setWordWrap(True)
        inner.addWidget(hint, r, 1)
        r += 1

        # Collapse/expand children when the group is toggled. Widgets added
        # at this point are direct children of `box`; layout recalcs on
        # visibility change.
        def _toggle(expanded: bool):
            for child in box.findChildren(QWidget):
                child.setVisible(expanded)

        box.toggled.connect(_toggle)
        _toggle(False)
        return box

    # ── recent episodes ──────────────────────────────────────

    def _build_episodes_table(self) -> QTableWidget:
        tbl = QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["Date", "Title", "Status"])
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setShowGrid(False)
        tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(0, 90)
        tbl.setColumnWidth(2, 90)

        with self.ctx.state._conn() as c:
            rows = c.execute(
                "SELECT guid, pub_date, title, status "
                "FROM episodes WHERE show_slug=? "
                "ORDER BY pub_date DESC LIMIT 10",
                (self.slug,),
            ).fetchall()

        tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            date_item = QTableWidgetItem((r["pub_date"] or "")[:10])
            date_item.setFont(QFont("Menlo"))
            # Stash guid on the date cell — retrievable from the context menu.
            date_item.setData(Qt.ItemDataRole.UserRole, r["guid"])
            tbl.setItem(i, 0, date_item)
            tbl.setItem(i, 1, QTableWidgetItem(r["title"] or ""))
            status = (r["status"] or "").lower()
            kind = _STATUS_PILL_KIND.get(status, "idle")
            pill = Pill(status or "—", kind=kind)
            # Wrap pill in container so table cell padding looks right.
            holder = QWidget()
            lay = QHBoxLayout(holder)
            lay.setContentsMargins(4, 2, 4, 2)
            lay.addWidget(pill)
            lay.addStretch(1)
            tbl.setCellWidget(i, 2, holder)

        # Size so ~10 rows are visible within the 440-tall dialog.
        tbl.setMinimumHeight(140)
        tbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Right-click on a row → "Re-transcribe this episode".
        self._episodes_tbl = tbl
        tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tbl.customContextMenuRequested.connect(self._on_episode_context_menu)
        return tbl

    def _on_episode_context_menu(self, pos) -> None:
        tbl = self._episodes_tbl
        index = tbl.indexAt(pos)
        if not index.isValid():
            return
        date_item = tbl.item(index.row(), 0)
        if date_item is None:
            return
        guid = date_item.data(Qt.ItemDataRole.UserRole)
        if not guid:
            return
        menu = QMenu(self)
        menu.addAction(
            "Re-transcribe this episode",
            lambda g=guid: self._retranscribe(g),
        )
        md_path = self._md_path_for(guid)
        if md_path is not None:
            bak = md_path.with_suffix(".md.bak")
            if bak.exists() and md_path.exists():
                menu.addAction(
                    "View diff",
                    lambda b=bak, cur=md_path: self._open_diff(b, cur),
                )
        menu.exec(tbl.viewport().mapToGlobal(pos))

    def _md_path_for(self, guid: str) -> Path | None:
        """Mirror `ui.retranscribe` path derivation so diff sees the same file."""
        from core.pipeline import build_slug

        ep = self.ctx.state.get_episode(guid)
        if ep is None:
            return None
        try:
            output_root = Path(self.ctx.settings.output_root).expanduser()
        except Exception:
            return None
        slug = build_slug(ep.get("pub_date") or "", ep.get("title") or "", "0000")
        return output_root / ep["show_slug"] / f"{slug}.md"

    def _open_diff(self, old: Path, new: Path) -> None:
        from ui.transcript_diff_dialog import TranscriptDiffDialog

        TranscriptDiffDialog(old, new, parent=self).exec()

    def _retranscribe(self, guid: str) -> None:
        retranscribe_episode(self.ctx, guid)
        # Refresh backlog label so the user sees the bump take effect.
        self.backlog_lbl.setText(self._fmt_backlog())

    # ── footer ───────────────────────────────────────────────

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        remove = QPushButton("Remove")
        remove.setProperty("role", "ghost")
        remove.setStyleSheet("QPushButton { color: #b04040; }")
        remove.clicked.connect(self._remove)
        row.addWidget(remove)

        mark_stale = QPushButton("Mark stale")
        mark_stale.setProperty("role", "ghost")
        mark_stale.clicked.connect(self._mark_stale)
        row.addWidget(mark_stale)

        row.addStretch(1)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)

        save = QPushButton("Save")
        save.setProperty("role", "primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(save)

        return row

    # ── actions ──────────────────────────────────────────────

    def _save(self):
        self.show_.rss = self.rss_edit.text().strip()
        self.show_.enabled = self.enabled_toggle.isChecked()
        out = self.output_edit.text().strip()
        self.show_.output_override = out or None
        # Advanced — tuning
        new_title = self._title_edit.text().strip()
        if new_title:
            self.show_.title = new_title
        self.show_.language = self._language_combo.currentData() or "de"
        self.show_.whisper_prompt = self._whisper_prompt_edit.toPlainText().strip()
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        self.accept()

    def _mark_stale(self):
        with self.ctx.state._conn() as c:
            c.execute(
                "UPDATE episodes SET status='pending' WHERE show_slug=?",
                (self.slug,),
            )
        QMessageBox.information(
            self,
            "Marked stale",
            f"All episodes of '{self.show_.title}' were marked pending.",
        )
        # Refresh the backlog label in-place so the user sees the effect.
        self.backlog_lbl.setText(self._fmt_backlog())

    def _remove(self):
        resp = QMessageBox.question(
            self,
            "Remove show",
            f"Remove '{self.show_.title}' from the watchlist?\n"
            "Existing transcripts on disk are not deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if resp != QMessageBox.StandardButton.Yes:
            return
        self.ctx.watchlist.shows = [s for s in self.ctx.watchlist.shows if s.slug != self.slug]
        self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
        self.accept()
