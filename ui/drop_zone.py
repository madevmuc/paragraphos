"""Drop-target widget for the v1.3 universal-ingest feature.

A card on the Shows page shows the prompt and hosts the URL input. It
doubles as a dispatcher for the main window's global ``dropEvent`` so
a user can drag a file anywhere and it still works.

Ingest work (SHA-256 hashing, yt-dlp probe) is dispatched to
``QThreadPool.globalInstance()`` so the UI stays responsive even for
large files or slow URL probes. Mirrors the ``QRunnable`` pattern used
by ``ui.feed_probe``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.local_source import IngestError, ingest_file, ingest_url
from core.state import StateStore

logger = logging.getLogger(__name__)


class _IngestSignals(QObject):
    # (guid, None) on success; (None, error_detail) on failure.
    done = pyqtSignal(object, object)


class _IngestRunnable(QRunnable):
    """Runs ``ingest_file`` or ``ingest_url`` off the main thread."""

    def __init__(self, kind: str, payload, **kw) -> None:
        super().__init__()
        self._kind = kind  # "file" | "url"
        self._payload = payload
        self._kw = kw
        self._signals = _IngestSignals()
        self.done = self._signals.done

    def run(self) -> None:
        try:
            if self._kind == "file":
                guid = ingest_file(self._payload, **self._kw)
            else:
                guid = ingest_url(self._payload, **self._kw)
        except IngestError as e:
            self._signals.done.emit(None, str(e))
            return
        except Exception as e:  # pragma: no cover — defensive
            logger.exception("drop-zone ingest crashed")
            self._signals.done.emit(None, f"unexpected error: {e}")
            return
        self._signals.done.emit(guid, None)


class DropZone(QFrame):
    """Visible drop target with a URL line-edit."""

    ingested = pyqtSignal(str)  # guid

    def __init__(
        self,
        *,
        state: StateStore,
        watchlist_path: Path,
        max_duration_hours: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._wl_path = watchlist_path
        self._max_hours = max_duration_hours
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        root = QVBoxLayout(self)
        title = QLabel("Drop an audio or video file here — or paste a URL")
        title.setStyleSheet("font-weight: 600;")
        root.addWidget(title)

        hint = QLabel(
            "Supports .mp3 / .m4a / .wav / .mp4 / .mov / .mkv / .webm / … "
            "and any URL yt-dlp recognises."
        )
        hint.setStyleSheet("color: palette(mid);")
        root.addWidget(hint)

        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        url_row.addWidget(self._url_edit, 1)
        self._go_btn = QPushButton("Ingest URL")
        self._go_btn.clicked.connect(self._on_go_clicked)
        url_row.addWidget(self._go_btn)
        root.addLayout(url_row)

        # Keep a reference to in-flight runnables so Qt doesn't GC their
        # signals before the emit lands on the main thread.
        self._pending: list[_IngestRunnable] = []

    # ── Qt drop plumbing ────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        md = event.mimeData()
        paths: list[Path] = []
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    paths.append(Path(u.toLocalFile()))
        if paths:
            self.handle_paths(paths)
            event.acceptProposedAction()
            return
        if md.hasText():
            text = md.text().strip()
            if text.startswith(("http://", "https://")):
                self.handle_url(text)
                event.acceptProposedAction()
                return

    # ── entry points for UI glue + tests ────────────────────────────────

    def handle_paths(self, paths: Iterable[Path]) -> None:
        for p in paths:
            self._submit(
                _IngestRunnable(
                    "file",
                    p,
                    show_slug=None,
                    state=self._state,
                    watchlist_path=self._wl_path,
                    source="local-drop",
                    max_duration_hours=self._max_hours,
                ),
                label=p.name,
            )

    def handle_url(self, url: str) -> None:
        self._go_btn.setEnabled(False)
        r = _IngestRunnable(
            "url",
            url,
            show_slug=None,
            state=self._state,
            watchlist_path=self._wl_path,
        )

        # Re-enable the button + clear the line-edit on success.
        def _after(guid, err, _url=url):
            self._go_btn.setEnabled(True)
            if err is None:
                self._url_edit.clear()

        r.done.connect(_after)
        self._submit(r, label=url)

    # ── internals ───────────────────────────────────────────────────────

    def _submit(self, runnable: _IngestRunnable, *, label: str) -> None:
        self._pending.append(runnable)

        def _handle(guid, err, _label=label, _r=runnable):
            try:
                self._pending.remove(_r)
            except ValueError:
                pass
            if err is not None:
                QMessageBox.warning(self, "Can't ingest", f"{_label}: {err}")
                return
            self.ingested.emit(guid)

        runnable.done.connect(_handle)
        QThreadPool.globalInstance().start(runnable)

    def _on_go_clicked(self) -> None:
        text = self._url_edit.text().strip()
        if text:
            self.handle_url(text)
