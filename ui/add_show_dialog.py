"""Add Podcast dialog — 3-mode segmented input (by name / by URL / Apple link).

All three modes funnel through `_do_save(show_dict)`, preserving the original
seeding logic (backlog strategy, manifest upsert).
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.discovery import find_rss_from_url, search_itunes
from core.models import Show
from core.prompt_gen import suggest_whisper_prompt
from core.rss import FeedHealth, build_manifest_with_url, feed_metadata
from ui.themes import current_tokens
from ui.widgets.pill import Pill

# --------------------------------------------------------------------------- #
# Background fetchers                                                         #
# --------------------------------------------------------------------------- #


class _FeedFetchThread(QThread):
    """Fetch feed_metadata + build_manifest_with_url + FeedHealth off-thread."""

    done = pyqtSignal(dict)  # {ok, rss, meta, manifest, health, error}

    def __init__(self, rss_url: str, parent=None):
        super().__init__(parent)
        self.rss_url = rss_url

    def run(self) -> None:
        out: dict = {"ok": False, "rss": self.rss_url}
        try:
            meta = feed_metadata(self.rss_url)
            canonical, manifest, _etag, _modified = build_manifest_with_url(self.rss_url)
            health = FeedHealth.check(canonical)
            out.update(
                {
                    "ok": True,
                    "rss": canonical,
                    "meta": meta,
                    "manifest": manifest,
                    "health": health,
                }
            )
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)
        self.done.emit(out)


class _AppleResolveThread(QThread):
    """Resolve an Apple Podcasts (or generic) landing URL → RSS URL."""

    done = pyqtSignal(dict)  # {ok, rss, error}

    def __init__(self, apple_url: str, parent=None):
        super().__init__(parent)
        self.apple_url = apple_url

    def run(self) -> None:
        out: dict = {"ok": False}
        try:
            rss = find_rss_from_url(self.apple_url)
            if not rss:
                out["error"] = "No RSS link found on that page."
            else:
                out.update({"ok": True, "rss": rss})
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)
        self.done.emit(out)


# --------------------------------------------------------------------------- #
# Dialog                                                                      #
# --------------------------------------------------------------------------- #


def _shorten(url: str, n: int = 48) -> str:
    return url if len(url) <= n else url[: n - 1] + "\u2026"


class AddShowDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.updated_watchlist = ctx.watchlist
        self.setWindowTitle("Add Podcast")
        self.resize(750, 640)

        # Shared state across modes
        self._loaded_manifest: list = []
        self._loaded_meta: dict = {}
        self._loaded_rss: str = ""
        self._fetch_thread: Optional[QThread] = None
        self._apple_thread: Optional[QThread] = None
        # Name-mode pagination: track last search so 'Load 50 more' knows
        # what to re-query; limit grows by 50 per click up to iTunes' 200 cap.
        self._name_search_term: str = ""
        self._name_search_limit: int = 50

        root = QVBoxLayout(self)

        # --- Segmented mode switcher -------------------------------------- #
        mode_row = QHBoxLayout()
        self._mode_buttons = QButtonGroup(self)
        self._mode_buttons.setExclusive(True)
        for key, label in (
            ("name", "By name"),
            ("url", "By URL"),
            ("apple", "Paste Apple link"),
        ):
            b = QRadioButton(label)
            b.setProperty("mode", key)
            mode_row.addWidget(b)
            self._mode_buttons.addButton(b)
        mode_row.addStretch(1)
        self._mode_buttons.buttons()[0].setChecked(True)
        self._mode_buttons.buttonToggled.connect(self._on_mode_change)
        root.addLayout(mode_row)

        # --- Stacked pages ------------------------------------------------- #
        self._pages = QStackedWidget()
        self._page_name = self._build_name_page()
        self._page_url = self._build_url_page()
        self._page_apple = self._build_apple_page()
        for p in (self._page_name, self._page_url, self._page_apple):
            self._pages.addWidget(p)
        root.addWidget(self._pages, 1)

    # ------------------------------------------------------------------ #
    # Mode switching                                                     #
    # ------------------------------------------------------------------ #

    def _on_mode_change(self, button, checked: bool) -> None:
        if not checked:
            return
        key = button.property("mode")
        idx = {"name": 0, "url": 1, "apple": 2}.get(key, 0)
        self._pages.setCurrentIndex(idx)

    # ------------------------------------------------------------------ #
    # Mode A — By name (iTunes search, preserved behavior)               #
    # ------------------------------------------------------------------ #

    def _build_name_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(QLabel("Search iTunes for a podcast by name:"))
        row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Lex Fridman Podcast")
        self.name_input.returnPressed.connect(self._search_by_name)
        row.addWidget(self.name_input, 1)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._search_by_name)
        row.addWidget(search_btn)
        v.addLayout(row)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self._pick_name_result)
        # Auto-fetch the next page when the user scrolls within ~60 px of
        # the bottom. A visible button interrupts the flow; an infinite-
        # scroll feel is closer to what the app's users expect.
        self.results.verticalScrollBar().valueChanged.connect(self._maybe_auto_load_more)
        v.addWidget(self.results, 1)

        self._name_hint = QLabel("")
        self._name_hint.setStyleSheet(f"color: {current_tokens()['ink_3']}; font-size: 11px;")
        v.addWidget(self._name_hint)
        self._name_fetch_in_flight = False

        form = QFormLayout()
        self.name_slug = QLineEdit()
        self.name_title = QLineEdit()
        self.name_rss = QLineEdit()
        self.name_prompt = QTextEdit()
        self.name_prompt.setFixedHeight(80)
        form.addRow("Slug", self.name_slug)
        form.addRow("Title", self.name_title)
        form.addRow("RSS", self.name_rss)
        form.addRow("Whisper prompt", self.name_prompt)
        v.addLayout(form)

        v.addLayout(self._backlog_row("name"))
        v.addLayout(self._button_row(on_add=self._add_from_name))
        return page

    def _search_by_name(self) -> None:
        term = self.name_input.text().strip()
        if not term:
            return
        self.results.clear()
        self._name_hint.setText("")
        self._name_search_term = term
        self._name_search_limit = 50
        try:
            if term.startswith("http"):
                # Convenience: pasted a URL in the name mode.
                rss = find_rss_from_url(term)
                if rss:
                    self._fill_from_feed_sync(rss)
                    return
                QMessageBox.warning(self, "Not found", "No RSS link on that page.")
                return
            self._render_name_results(search_itunes(term, limit=self._name_search_limit))
            if self.results.count() == 0:
                QMessageBox.information(self, "No matches", "iTunes returned no results.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Error", str(e))

    def _render_name_results(self, matches) -> None:
        """Fill the list widget and update the hint.

        Called on initial search and on every scroll-triggered auto-load —
        we replace the full list rather than append because iTunes doesn't
        guarantee stable ordering across calls, so a superset request may
        reshuffle earlier positions.
        """
        # Preserve scroll position across re-renders so an auto-load
        # triggered at the bottom doesn't jerk the viewport back to the top.
        scroll_val = self.results.verticalScrollBar().value()
        self.results.clear()
        for m in matches:
            item = QListWidgetItem(f"{m.title} — {m.author}")
            item.setData(Qt.ItemDataRole.UserRole, m.feed_url)
            self.results.addItem(item)
        self.results.verticalScrollBar().setValue(scroll_val)
        shown = self.results.count()
        # iTunes caps at 200 and returns fewer when the query is narrow.
        hit_api_cap = self._name_search_limit >= 200
        capped_by_server = shown < self._name_search_limit
        if capped_by_server or hit_api_cap:
            self._name_hint.setText(f"Showing all {shown} matches.")
        else:
            self._name_hint.setText(f"Showing top {shown} · scroll for more.")

    def _maybe_auto_load_more(self, _value: int) -> None:
        """Trigger the next page when the user scrolls near the bottom.

        Gated on (a) a search term is set, (b) we haven't hit the 200-item
        iTunes cap, (c) the last fetch filled the requested limit (server
        hasn't signalled exhaustion), and (d) no fetch is already running.
        """
        if self._name_fetch_in_flight:
            return
        if not self._name_search_term:
            return
        if self._name_search_limit >= 200:
            return
        shown = self.results.count()
        if shown == 0 or shown < self._name_search_limit:
            return  # server returned fewer than requested — no more to get.
        sb = self.results.verticalScrollBar()
        if sb.value() < sb.maximum() - 2:
            return  # not at (or within epsilon of) the bottom yet.
        self._load_more_name_results()

    def _load_more_name_results(self) -> None:
        if not self._name_search_term:
            return
        self._name_fetch_in_flight = True
        self._name_hint.setText("Loading more…")
        self._name_search_limit = min(self._name_search_limit + 50, 200)
        try:
            self._render_name_results(
                search_itunes(self._name_search_term, limit=self._name_search_limit)
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self._name_fetch_in_flight = False

    def _pick_name_result(self, item: QListWidgetItem) -> None:
        self._fill_from_feed_sync(item.data(Qt.ItemDataRole.UserRole))

    def _fill_from_feed_sync(self, rss: str) -> None:
        try:
            meta = feed_metadata(rss)
            canonical, manifest, _etag, _modified = build_manifest_with_url(rss)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Error", str(e))
            return
        self.name_rss.setText(canonical)
        self.name_title.setText(meta["title"])
        default_slug = (meta["title"] or "show").lower().replace(" ", "-")
        self.name_slug.setText(default_slug)
        prompt = suggest_whisper_prompt(
            title=meta["title"],
            author=meta["author"],
            episodes=[
                {"title": e["title"], "description": e["description"]} for e in manifest[-20:]
            ],
        )
        self.name_prompt.setPlainText(prompt)
        self._loaded_manifest = manifest
        self._loaded_meta = meta
        self._loaded_rss = canonical

    def _add_from_name(self) -> None:
        show = {
            "slug": self.name_slug.text().strip(),
            "title": self.name_title.text().strip(),
            "rss": self.name_rss.text().strip(),
            "whisper_prompt": self.name_prompt.toPlainText().strip(),
            "manifest": self._loaded_manifest,
            "backlog": self._backlog_choice("name"),
            "artwork_url": (self._loaded_meta or {}).get("artwork_url", ""),
        }
        self._do_save(show)

    # ------------------------------------------------------------------ #
    # Mode B — By URL                                                    #
    # ------------------------------------------------------------------ #

    def _build_url_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(QLabel("Paste an RSS feed URL:"))
        row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/podcast.rss")
        self.url_input.editingFinished.connect(self._fetch_url_preview)
        row.addWidget(self.url_input, 1)
        fetch_btn = QPushButton("Preview")
        fetch_btn.clicked.connect(self._fetch_url_preview)
        row.addWidget(fetch_btn)
        v.addLayout(row)

        self.url_status = Pill("", kind="idle")
        self.url_status.setVisible(False)
        v.addWidget(self.url_status, 0, Qt.AlignmentFlag.AlignLeft)

        # Preview card
        self.url_card = QFrame()
        self.url_card.setObjectName("PreviewCard")
        self.url_card.setFrameShape(QFrame.Shape.StyledPanel)
        self.url_card.setVisible(False)
        card_v = QVBoxLayout(self.url_card)

        self.url_card_title = QLabel("")
        f = self.url_card_title.font()
        f.setPointSize(f.pointSize() + 4)
        f.setBold(True)
        self.url_card_title.setFont(f)
        self.url_card_title.setWordWrap(True)
        card_v.addWidget(self.url_card_title)

        self.url_card_publisher = QLabel("")
        self.url_card_publisher.setStyleSheet(f"color: {current_tokens()['ink_3']};")
        self.url_card_publisher.setWordWrap(True)
        card_v.addWidget(self.url_card_publisher)

        self.url_card_meta = QLabel("")
        card_v.addWidget(self.url_card_meta)

        self.url_card_warnings = QLabel("")
        self.url_card_warnings.setStyleSheet(f"color: {current_tokens()['danger']};")
        self.url_card_warnings.setWordWrap(True)
        self.url_card_warnings.setVisible(False)
        card_v.addWidget(self.url_card_warnings)

        v.addWidget(self.url_card)
        v.addStretch(1)

        v.addLayout(self._backlog_row("url"))
        self.url_add_btn_row = self._button_row(
            on_add=self._add_from_url, add_enabled=False, store_add_on="url"
        )
        v.addLayout(self.url_add_btn_row)
        return page

    def _fetch_url_preview(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            QMessageBox.warning(self, "Invalid URL", "Please enter an http(s) URL.")
            return
        if self._fetch_thread and self._fetch_thread.isRunning():
            return
        self.url_status.setText("Fetching feed…")
        self.url_status.set_kind("running")
        self.url_status.setVisible(True)
        self.url_card.setVisible(False)
        self._url_add_btn.setEnabled(False)

        self._fetch_thread = _FeedFetchThread(url, self)
        self._fetch_thread.done.connect(self._on_url_fetched)
        self._fetch_thread.start()

    def _on_url_fetched(self, result: dict) -> None:
        if not result.get("ok"):
            self.url_status.setText(f"Error: {result.get('error', 'unknown')}")
            self.url_status.set_kind("fail")
            return
        meta = result["meta"]
        manifest = result["manifest"]
        health: FeedHealth = result["health"]
        rss = result["rss"]

        self._loaded_meta = meta
        self._loaded_manifest = manifest
        self._loaded_rss = rss

        self.url_card_title.setText(meta.get("title") or "(untitled)")
        self.url_card_publisher.setText(meta.get("author") or "")
        latest = manifest[-1]["pubDate"][:10] if manifest else "—"
        self.url_card_meta.setText(f"{len(manifest)} episode(s) · latest: {latest}")
        warnings = []
        if not health.ok:
            warnings.append(f"Feed health: {health.reason}")
        if not manifest:
            warnings.append("No episodes with audio enclosures were found.")
        if warnings:
            self.url_card_warnings.setText(" · ".join(warnings))
            self.url_card_warnings.setVisible(True)
        else:
            self.url_card_warnings.setVisible(False)

        self.url_card.setVisible(True)
        self.url_status.setText("Ready")
        self.url_status.set_kind("ok")
        self._url_add_btn.setEnabled(bool(manifest))

    def _add_from_url(self) -> None:
        meta = self._loaded_meta
        title = meta.get("title") or "show"
        slug = title.lower().replace(" ", "-")
        prompt = suggest_whisper_prompt(
            title=title,
            author=meta.get("author", ""),
            episodes=[
                {"title": e["title"], "description": e["description"]}
                for e in self._loaded_manifest[-20:]
            ],
        )
        show = {
            "slug": slug,
            "title": title,
            "rss": self._loaded_rss,
            "whisper_prompt": prompt,
            "manifest": self._loaded_manifest,
            "backlog": self._backlog_choice("url"),
            "artwork_url": meta.get("artwork_url", ""),
        }
        self._do_save(show)

    # ------------------------------------------------------------------ #
    # Mode C — Paste Apple link                                          #
    # ------------------------------------------------------------------ #

    def _build_apple_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)

        v.addWidget(QLabel("Paste an Apple Podcasts link:"))
        row = QHBoxLayout()
        self.apple_input = QLineEdit()
        self.apple_input.setPlaceholderText("https://podcasts.apple.com/…/id1234567890")
        self.apple_input.editingFinished.connect(self._detect_apple)
        row.addWidget(self.apple_input, 1)
        detect_btn = QPushButton("Detect RSS")
        detect_btn.clicked.connect(self._detect_apple)
        row.addWidget(detect_btn)
        v.addLayout(row)

        self.apple_status = Pill("", kind="idle")
        self.apple_status.setVisible(False)
        v.addWidget(self.apple_status, 0, Qt.AlignmentFlag.AlignLeft)

        # Dashed-border compact card
        self.apple_card = QFrame()
        self.apple_card.setObjectName("ApplePreviewCard")
        _t = current_tokens()
        self.apple_card.setStyleSheet(
            f"QFrame#ApplePreviewCard {{ border: 1px dashed {_t['line']}; "
            f"border-radius: 6px; padding: 8px; }}"
        )
        self.apple_card.setVisible(False)
        card_v = QVBoxLayout(self.apple_card)
        self.apple_card_title = QLabel("")
        f = self.apple_card_title.font()
        f.setBold(True)
        self.apple_card_title.setFont(f)
        self.apple_card_title.setWordWrap(True)
        card_v.addWidget(self.apple_card_title)
        self.apple_card_rss = QLabel("")
        self.apple_card_rss.setStyleSheet(f"color: {_t['ink_3']};")
        self.apple_card_rss.setWordWrap(True)
        card_v.addWidget(self.apple_card_rss)
        v.addWidget(self.apple_card)
        v.addStretch(1)

        v.addLayout(self._backlog_row("apple", default="Last 5"))

        # Custom button row with "Customise…" instead of just Cancel/Add
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self.apple_customise_btn = QPushButton("Customise…")
        self.apple_customise_btn.setEnabled(False)
        self.apple_customise_btn.clicked.connect(self._customise_from_apple)
        btn_row.addWidget(self.apple_customise_btn)
        self.apple_add_btn = QPushButton("Add")
        self.apple_add_btn.setDefault(True)
        self.apple_add_btn.setEnabled(False)
        self.apple_add_btn.clicked.connect(self._add_from_apple)
        btn_row.addWidget(self.apple_add_btn)
        v.addLayout(btn_row)
        return page

    def _detect_apple(self) -> None:
        url = self.apple_input.text().strip()
        if not url:
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            QMessageBox.warning(self, "Invalid URL", "Please enter an http(s) URL.")
            return
        if self._apple_thread and self._apple_thread.isRunning():
            return
        self.apple_status.setText("Detecting RSS…")
        self.apple_status.set_kind("running")
        self.apple_status.setVisible(True)
        self.apple_card.setVisible(False)
        self.apple_add_btn.setEnabled(False)
        self.apple_customise_btn.setEnabled(False)

        self._apple_thread = _AppleResolveThread(url, self)
        self._apple_thread.done.connect(self._on_apple_resolved)
        self._apple_thread.start()

    def _on_apple_resolved(self, result: dict) -> None:
        if not result.get("ok"):
            self.apple_status.setText(f"Error: {result.get('error', 'unknown')}")
            self.apple_status.set_kind("fail")
            return
        rss = result["rss"]
        # Now pull metadata (lightweight second hop).
        self._fetch_thread = _FeedFetchThread(rss, self)
        self._fetch_thread.done.connect(self._on_apple_feed_fetched)
        self.apple_status.setText("Loading feed…")
        self.apple_status.set_kind("running")
        self._fetch_thread.start()

    def _on_apple_feed_fetched(self, result: dict) -> None:
        if not result.get("ok"):
            self.apple_status.setText(f"Error: {result.get('error', 'unknown')}")
            self.apple_status.set_kind("fail")
            return
        meta = result["meta"]
        self._loaded_meta = meta
        self._loaded_manifest = result["manifest"]
        self._loaded_rss = result["rss"]
        self.apple_card_title.setText(meta.get("title") or "(untitled)")
        self.apple_card_rss.setText(f"RSS detected at {_shorten(result['rss'])}")
        self.apple_card.setVisible(True)
        self.apple_status.setText("Ready")
        self.apple_status.set_kind("ok")
        self.apple_add_btn.setEnabled(bool(self._loaded_manifest))
        self.apple_customise_btn.setEnabled(True)

    def _add_from_apple(self) -> None:
        meta = self._loaded_meta
        title = meta.get("title") or "show"
        slug = title.lower().replace(" ", "-")
        prompt = suggest_whisper_prompt(
            title=title,
            author=meta.get("author", ""),
            episodes=[
                {"title": e["title"], "description": e["description"]}
                for e in self._loaded_manifest[-20:]
            ],
        )
        show = {
            "slug": slug,
            "title": title,
            "rss": self._loaded_rss,
            "whisper_prompt": prompt,
            "manifest": self._loaded_manifest,
            "backlog": self._backlog_choice("apple"),
            "artwork_url": meta.get("artwork_url", ""),
        }
        self._do_save(show)

    def _customise_from_apple(self) -> None:
        """Jump to Mode A pre-filled with the detected feed."""
        # Switch mode
        self._mode_buttons.buttons()[0].setChecked(True)
        # Pre-fill search term from detected title + pre-run the search.
        title = (self._loaded_meta or {}).get("title", "")
        if title:
            self.name_input.setText(title)
            self._search_by_name()
        # Also pre-fill the form fields directly from the resolved feed, so
        # the user can hit Add immediately without picking a search result.
        if self._loaded_rss:
            self._fill_from_feed_sync(self._loaded_rss)

    # ------------------------------------------------------------------ #
    # Common: backlog toggle, button row, save funnel                    #
    # ------------------------------------------------------------------ #

    def _backlog_row(self, key: str, default: str = "Last 5") -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Backlog:"))
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for label in ("Last 5", "Last 10", "All"):
            b = QRadioButton(label)
            if label == default:
                b.setChecked(True)
            grp.addButton(b)
            row.addWidget(b)
        row.addStretch(1)
        setattr(self, f"_backlog_grp_{key}", grp)
        return row

    def _backlog_choice(self, key: str) -> str:
        grp: QButtonGroup = getattr(self, f"_backlog_grp_{key}")
        btn = grp.checkedButton()
        return btn.text() if btn else "Last 5"

    def _button_row(
        self, *, on_add, add_enabled: bool = True, store_add_on: Optional[str] = None
    ) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        add = QPushButton("Add")
        add.setDefault(True)
        add.setEnabled(add_enabled)
        add.clicked.connect(on_add)
        row.addWidget(add)
        if store_add_on:
            setattr(self, f"_{store_add_on}_add_btn", add)
        return row

    # ------------------------------------------------------------------ #
    # Save funnel — logic preserved from the pre-rewrite dialog          #
    # ------------------------------------------------------------------ #

    def _do_save(self, show: dict) -> None:
        slug = (show.get("slug") or "").strip()
        if not slug:
            QMessageBox.warning(self, "Missing", "Slug required.")
            return
        if any(s.slug == slug for s in self.updated_watchlist.shows):
            QMessageBox.warning(self, "Exists", f"{slug!r} is already in the watchlist.")
            return
        rss = (show.get("rss") or "").strip()
        if not rss:
            QMessageBox.warning(self, "Missing", "RSS URL required.")
            return

        model = Show(
            slug=slug,
            title=(show.get("title") or "").strip() or slug,
            rss=rss,
            whisper_prompt=(show.get("whisper_prompt") or "").strip(),
            artwork_url=(show.get("artwork_url") or "").strip(),
        )
        self.updated_watchlist.shows.append(model)
        self.updated_watchlist.save(self.ctx.data_dir / "watchlist.yaml")

        # Seed episodes in state; handle backlog strategy.
        manifest = show.get("manifest") or []
        for ep in manifest:
            self.ctx.state.upsert_episode(
                show_slug=slug,
                guid=ep["guid"],
                title=ep["title"],
                pub_date=ep["pubDate"],
                mp3_url=ep["mp3_url"],
            )

        mode = show.get("backlog") or "Last 5"
        if mode == "All":
            pass  # leave everything pending
        elif mode.startswith("Last "):
            n = int(mode.split()[1])
            with self.ctx.state._conn() as c:
                c.execute(
                    """
                    UPDATE episodes SET status='done'
                    WHERE show_slug=? AND guid NOT IN (
                        SELECT guid FROM episodes WHERE show_slug=?
                        ORDER BY pub_date DESC LIMIT ?
                    )""",
                    (slug, slug, n),
                )

        self.accept()
