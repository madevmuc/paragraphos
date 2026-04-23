"""Drop-target widget for the v1.3 universal-ingest feature.

A card on the Shows page shows the prompt and hosts the URL input. It
doubles as a dispatcher for the main window's global ``dropEvent`` so
a user can drag a file anywhere and it still works.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import pyqtSignal
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
        go = QPushButton("Ingest URL")
        go.clicked.connect(self._on_go_clicked)
        url_row.addWidget(go)
        root.addLayout(url_row)

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
            try:
                guid = ingest_file(
                    p,
                    show_slug=None,
                    state=self._state,
                    watchlist_path=self._wl_path,
                    source="local-drop",
                    max_duration_hours=self._max_hours,
                )
                self.ingested.emit(guid)
            except IngestError as e:
                QMessageBox.warning(self, "Can't ingest", f"{p.name}: {e}")

    def handle_url(self, url: str) -> None:
        try:
            guid = ingest_url(
                url,
                show_slug=None,
                state=self._state,
                watchlist_path=self._wl_path,
            )
            self.ingested.emit(guid)
            self._url_edit.clear()
        except IngestError as e:
            QMessageBox.warning(self, "Can't ingest URL", str(e))

    def _on_go_clicked(self) -> None:
        text = self._url_edit.text().strip()
        if text:
            self.handle_url(text)
