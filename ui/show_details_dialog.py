"""Per-show details dialog — opens on row-double-click in Shows tab.

Restyled for v1.0 ship: fixed 620×440 dialog with an artwork header, a
120 px / flex form grid, a last-10 recent-episodes table with status
`Pill`s, and a footer row (Remove · Mark stale · Save).

Save / remove / mark-stale logic is preserved from the previous revision
— only the layout and widget composition changed.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPainterPath, QPixmap
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
from ui.prioritize import (
    PRIORITY_RUN_NEXT,
    PRIORITY_RUN_NOW,
    bump_priority,
    can_bump,
)
from ui.retranscribe import retranscribe_episode
from ui.themes import current_tokens
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


class _FeedMetadataThread(QThread):
    """Short-lived worker: fetches RSS channel metadata off the UI thread.

    Emits `ok(dict)` on success or `err(str)` on failure. The dialog owns the
    instance (kept as `self._metadata_thread`) so it isn't GC'd mid-flight.
    """

    ok = pyqtSignal(dict)
    err = pyqtSignal(str)

    def __init__(self, url: str, timeout: float = 15.0, parent=None):
        super().__init__(parent)
        self._url = url
        self._timeout = timeout

    def run(self) -> None:  # noqa: D401 — QThread entry
        from core.rss import feed_metadata

        try:
            meta = feed_metadata(self._url, timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001 — surfaced via signal
            self.err.emit(str(exc))
            return
        self.ok.emit(meta or {})


class _ArtworkFetchThread(QThread):
    """Short-lived worker: downloads (or reads from cache) cover art.

    Emits ``ready(Path)`` on success or ``missing()`` on any failure —
    the dialog keeps showing the 🎙 placeholder when missing fires, so
    we don't need to distinguish error types.
    """

    ready = pyqtSignal(object)  # pathlib.Path
    missing = pyqtSignal()

    def __init__(self, slug: str, url: str, parent=None):
        super().__init__(parent)
        self._slug = slug
        self._url = url

    def run(self) -> None:  # noqa: D401 — QThread entry
        from core.artwork import ensure_artwork

        path = ensure_artwork(self._slug, self._url)
        if path is None:
            self.missing.emit()
        else:
            self.ready.emit(path)


def _rounded_pixmap(src: QPixmap, side: int, radius: int) -> QPixmap:
    """Crop ``src`` to a ``side``×``side`` square with rounded corners.

    Scaling is done with SmoothTransformation and the crop is centered so
    16:9 / portrait sources still look right in the 64 px frame.
    """
    scaled = src.scaled(
        side,
        side,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    # Centre-crop to square.
    x = (scaled.width() - side) // 2
    y = (scaled.height() - side) // 2
    cropped = scaled.copy(x, y, side, side)

    out = QPixmap(side, side)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, side, side, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, cropped)
    p.end()
    return out


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
        # Minimum size (not fixed): the dialog has to fit header + form +
        # collapsible Advanced + episodes table + footer. Fixed 440 h
        # clipped the footer off-screen on the v1.0.0 restyle.
        self.setMinimumSize(620, 560)
        self.resize(620, 560)

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
        _t = current_tokens()
        art.setStyleSheet(
            f"QLabel {{ background: {_t['surface_alt']};"
            f" border: 1px solid {_t['line']}; border-radius: 6px; }}"
        )
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Placeholder glyph — stays on screen until (and unless) the
        # async artwork fetch resolves with a real pixmap. Keeps the
        # dialog render cleanly when the feed exposes no cover art.
        art.setText("🎙")
        art.setObjectName("ShowArtwork")
        self._artwork_label = art
        row.addWidget(art, 0, Qt.AlignmentFlag.AlignTop)

        # Kick off artwork load off-thread so dialog open isn't blocked
        # on a CDN round-trip. Cache hits still read from disk inside
        # ensure_artwork, but we always hop to a QThread for uniformity.
        self._maybe_load_artwork(getattr(self.show_, "artwork_url", "") or "")

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
        meta_text = f"{self.show_.slug} · {s.total} eps · {s.done} done · {s.pending} pending"
        meta = QLabel(meta_text)
        meta.setProperty("class", "muted")
        meta.setStyleSheet(f"color: {_t['ink_3']}; font-size: 11px;")
        text_col.addWidget(meta)

        feed = QLabel(self.show_.rss)
        feed.setStyleSheet(f"color: {_t['ink_3']}; font-family: Menlo, monospace; font-size: 11px;")
        feed.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_col.addWidget(feed)
        text_col.addStretch(1)

        row.addLayout(text_col, 1)

        # Right-hand "Refresh from feed" button — re-fetches feed metadata
        # (title, publisher, canonical URL) so the user can populate / sync
        # details without editing the row manually.
        self._refresh_btn = QPushButton("Refresh from feed")
        self._refresh_btn.setToolTip("Re-fetch RSS metadata and update fields")
        self._refresh_btn.clicked.connect(self._refresh_from_feed)
        row.addWidget(self._refresh_btn, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _maybe_load_artwork(self, url: str) -> None:
        """Start an async fetch of the cover art at ``url``.

        No-op when ``url`` is empty (leaves the 🎙 placeholder). Guards
        against starting a second fetch while one is already running —
        Refresh-from-feed can call this repeatedly.
        """
        if not url:
            return
        existing = getattr(self, "_artwork_thread", None)
        if existing is not None and existing.isRunning():
            return
        thread = _ArtworkFetchThread(self.slug, url, parent=self)
        thread.ready.connect(self._on_artwork_ready)
        thread.missing.connect(self._on_artwork_missing)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, "_artwork_thread", None))
        self._artwork_thread = thread
        thread.start()

    def _on_artwork_ready(self, path) -> None:
        lbl = getattr(self, "_artwork_label", None)
        if lbl is None:
            return
        pm = QPixmap(str(path))
        if pm.isNull():
            # File exists but isn't decodable — leave placeholder.
            return
        lbl.setText("")
        lbl.setPixmap(_rounded_pixmap(pm, 64, 6))

    def _on_artwork_missing(self) -> None:
        # Network or cache miss — placeholder is already rendered, nothing to do.
        return

    def _invalidate_artwork_cache(self) -> None:
        """Delete any cached artwork file for this slug so a fresh URL
        triggers a re-fetch on the next ``ensure_artwork`` call."""
        from core.artwork import artwork_dir

        d = artwork_dir()
        for ext in (".jpg", ".png", ".webp", ".gif", ".img"):
            p = d / f"{self.slug}{ext}"
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    def _refresh_from_feed(self) -> None:
        """Pull channel metadata off-thread and update editable fields.

        `feed_metadata` can block up to 15 s on slow CDNs, which would freeze
        the dialog if run on the UI thread. We spin up a short-lived
        `_FeedMetadataThread` and apply the result (or surface the error) in
        slots that run back on the UI thread.
        """
        # Guard against double-click while a previous refresh is still
        # in-flight.
        existing = getattr(self, "_metadata_thread", None)
        if existing is not None and existing.isRunning():
            return

        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Fetching…")

        thread = _FeedMetadataThread(self.rss_edit.text().strip(), timeout=15.0, parent=self)
        thread.ok.connect(self._on_refresh_ok)
        thread.err.connect(self._on_refresh_err)
        # Drop the reference once the thread is finished so we can start a new
        # one on the next click.
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, "_metadata_thread", None))
        self._metadata_thread = thread
        thread.start()

    def _on_refresh_ok(self, meta: dict) -> None:
        # Apply — only overwrite fields the feed actually supplied.
        title_changed = False
        if meta.get("title") and meta["title"] != self._title_edit.text():
            self._title_edit.setText(meta["title"])
            self.show_.title = meta["title"]
            title_changed = True
        canonical = meta.get("canonical_url")
        if canonical and canonical != self.rss_edit.text().strip():
            self.rss_edit.setText(canonical)
            self.show_.rss = canonical
        # Artwork: persist on the Show so a subsequent dialog open (or
        # watchlist save via _save) doesn't lose it. We also trigger an
        # async (re)load so the header updates in-place without the user
        # having to reopen the dialog.
        artwork_url = meta.get("artwork_url") or ""
        new_art = artwork_url and artwork_url != getattr(self.show_, "artwork_url", "")
        if artwork_url:
            self.show_.artwork_url = artwork_url
            if new_art:
                # URL changed — drop the cached file so ensure_artwork
                # fetches fresh bytes instead of returning the stale one.
                self._invalidate_artwork_cache()
            self._maybe_load_artwork(artwork_url)
        # Persist the updated Show to the watchlist so the Shows-tab row
        # reflects the new title/rss/artwork without the user having to
        # hit Save first. Best-effort — if ctx.data_dir isn't present we
        # fall through and the user can still click Save manually.
        try:
            self.ctx.watchlist.save(self.ctx.data_dir / "watchlist.yaml")
            parent = self.parent()
            while parent is not None:
                shows_tab = getattr(parent, "shows_tab", None)
                if shows_tab is not None:
                    shows_tab.refresh()
                    break
                parent = parent.parent()
        except Exception:
            pass
        # Advanced group is collapsed by default; if the refresh wrote a new
        # title there, pop the group open so the user sees what changed
        # before hitting Save.
        if title_changed and hasattr(self, "_advanced_box"):
            self._advanced_box.setChecked(True)
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("✓ Refreshed")
        QTimer.singleShot(1400, self._reset_refresh_btn_label)

    def _on_refresh_err(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Refresh failed",
            f"Could not fetch feed metadata:\n{message}",
        )
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("Refresh from feed")

    def _reset_refresh_btn_label(self) -> None:
        # Guarded: dialog may have been closed before the QTimer fires.
        if self._refresh_btn is not None:
            self._refresh_btn.setText("Refresh from feed")

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        """Ensure any in-flight metadata fetch is reaped before the dialog dies."""
        thread = getattr(self, "_metadata_thread", None)
        if thread is not None and thread.isRunning():
            # Disconnect slots so the thread's result can't touch a widget
            # that's being torn down.
            try:
                thread.ok.disconnect()
                thread.err.disconnect()
            except (TypeError, RuntimeError):
                pass
            thread.quit()
            thread.wait(2000)
        art_thread = getattr(self, "_artwork_thread", None)
        if art_thread is not None and art_thread.isRunning():
            try:
                art_thread.ready.disconnect()
                art_thread.missing.disconnect()
            except (TypeError, RuntimeError):
                pass
            # Artwork fetch is a single blocking httpx GET — give it up to
            # 3 s to unwind so we don't hang on dialog close.
            art_thread.quit()
            art_thread.wait(3000)
        super().closeEvent(event)

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
        _t = current_tokens()
        self.last_checked_lbl.setStyleSheet(f"color: {_t['ink_3']};")
        grid.addWidget(self.last_checked_lbl, r, 1)
        r += 1

        grid.addWidget(self._label("Backlog"), r, 0)
        self.backlog_lbl = QLabel(self._fmt_backlog())
        self.backlog_lbl.setStyleSheet(f"color: {_t['ink_3']};")
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
        # Let the themed QSS pick the color — inline palette(mid) rendered
        # white-on-white in dark mode because Qt's palette role doesn't
        # track our custom ThemeManager. Font size stays 12 px.
        lbl.setStyleSheet("font-size: 12px;")
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
        # Handle kept so _refresh_from_feed can pop the group open when it
        # writes a new title the user would otherwise not see.
        self._advanced_box = box

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
        # Stack the edit + its hint in a sub-layout so the hint can't
        # overlap the text edit when rows collapse.
        prompt_col = QVBoxLayout()
        prompt_col.setContentsMargins(0, 0, 0, 0)
        prompt_col.setSpacing(3)
        self._whisper_prompt_edit = QPlainTextEdit(self.show_.whisper_prompt or "")
        self._whisper_prompt_edit.setFixedHeight(80)
        prompt_col.addWidget(self._whisper_prompt_edit)
        hint = QLabel("Comma-separated hints (names, jargon, places). Improves recognition.")
        hint.setStyleSheet(f"color: {current_tokens()['ink_3']}; font-size: 11px;")
        hint.setWordWrap(True)
        prompt_col.addWidget(hint)
        prompt_wrap = QWidget()
        prompt_wrap.setLayout(prompt_col)
        inner.addWidget(prompt_wrap, r, 1)
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
            # Stash guid + status on the date cell — retrievable from the
            # context menu to gate priority-bump actions.
            date_item.setData(Qt.ItemDataRole.UserRole, r["guid"])
            date_item.setData(Qt.ItemDataRole.UserRole + 1, r["status"] or "")
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
        status = date_item.data(Qt.ItemDataRole.UserRole + 1) or ""
        menu = QMenu(self)
        menu.addAction(
            "Re-transcribe this episode",
            lambda g=guid: self._retranscribe(g),
        )
        if can_bump(status):
            menu.addSeparator()
            menu.addAction(
                "Run next",
                lambda g=guid: self._bump(g, PRIORITY_RUN_NEXT),
            )
            menu.addAction(
                "Run now",
                lambda g=guid: self._bump(g, PRIORITY_RUN_NOW),
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

    def _bump(self, guid: str, priority: int) -> None:
        bump_priority(self.ctx, guid, priority)
        # The recent-episodes table is ordered by pub_date so a priority
        # bump doesn't visually reorder rows here — but the backlog label
        # (pending/failed counts) is what the user watches on this dialog,
        # and the Queue tab (if visible elsewhere) will reorder on its
        # next refresh.
        self.backlog_lbl.setText(self._fmt_backlog())

    # ── footer ───────────────────────────────────────────────

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        remove = QPushButton("Remove")
        remove.setProperty("role", "ghost")
        remove.setStyleSheet(f"QPushButton {{ color: {current_tokens()['danger']}; }}")
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
