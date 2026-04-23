"""Top-level Local Transcript tab.

Three visually distinct zones:
  1. Big drag-drop area for local audio/video files.
  2. A button to open the Import-folder dialog (reuses
     ``ImportFolderDialog`` from ``ui.import_folder_dialog``).
  3. A URL line-edit + button to ingest via yt-dlp's generic extractor.

All three paths funnel into the existing ``core.local_source`` entry
points (``ingest_file``, ``ingest_folder``, ``ingest_url``) via a
``QRunnable`` worker on ``QThreadPool.globalInstance()`` so the UI
stays responsive for large files / slow URL probes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.local_source import IngestError, ingest_file, ingest_folder, ingest_url

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
            logger.exception("local-transcript ingest crashed")
            self._signals.done.emit(None, f"unexpected error: {e}")
            return
        self._signals.done.emit(guid, None)


class _DropSurface(QFrame):
    """Large drop-only panel. Emits ``dropped_paths(list)`` on a drop."""

    dropped_paths = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        v = QVBoxLayout(self)
        v.addStretch(1)
        title = QLabel("Drop an audio or video file here")
        title.setStyleSheet("font-weight: 600; font-size: 16px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        hint = QLabel(
            "Supports .mp3 / .m4a / .wav / .mp4 / .mov / .mkv / .webm / … "
            "and similar formats ffmpeg can decode."
        )
        hint.setStyleSheet("color: palette(mid);")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        v.addWidget(hint)
        v.addStretch(1)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        md = event.mimeData()
        paths: list[Path] = []
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    paths.append(Path(u.toLocalFile()))
        if paths:
            self.dropped_paths.emit(paths)
            event.acceptProposedAction()


class LocalTranscriptTab(QWidget):
    """Top-level tab for local-file / folder / URL ingest."""

    ingested = pyqtSignal(str)  # guid

    def __init__(self, ctx: "AppContext", parent: QWidget | None = None) -> None:  # noqa: F821
        super().__init__(parent)
        self._ctx = ctx
        self._pending: list[_IngestRunnable] = []
        self._build()

    # ── layout ─────────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(16)

        # Zone 1: big drop surface.
        self._drop_surface = _DropSurface(self)
        self._drop_surface.dropped_paths.connect(self.handle_paths)
        root.addWidget(self._drop_surface, stretch=1)

        # Zone 2: folder row.
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Or import every supported file in a folder:"))
        folder_row.addStretch(1)
        self._folder_btn = QPushButton("Choose folder to import…")
        self._folder_btn.clicked.connect(self._on_folder_clicked)
        folder_row.addWidget(self._folder_btn)
        root.addLayout(folder_row)

        # Zone 3: URL row.
        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Or ingest from a URL:"))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        self._url_edit.returnPressed.connect(self._on_url_clicked)
        url_row.addWidget(self._url_edit, 1)
        self._url_btn = QPushButton("Ingest URL")
        self._url_btn.clicked.connect(self._on_url_clicked)
        url_row.addWidget(self._url_btn)
        root.addLayout(url_row)

    # ── public entry points (also used by MainWindow global drop) ──────

    def handle_paths(self, paths: Iterable[Path]) -> None:
        max_hours = int(self._ctx.settings.local_max_duration_hours)
        wl_path = self._ctx.data_dir / "watchlist.yaml"
        for p in paths:
            self._submit(
                _IngestRunnable(
                    "file",
                    p,
                    show_slug=None,
                    state=self._ctx.state,
                    watchlist_path=wl_path,
                    source="local-drop",
                    max_duration_hours=max_hours,
                ),
                label=p.name,
            )

    def handle_url(self, url: str) -> None:
        self._url_btn.setEnabled(False)
        wl_path = self._ctx.data_dir / "watchlist.yaml"
        r = _IngestRunnable(
            "url",
            url,
            show_slug=None,
            state=self._ctx.state,
            watchlist_path=wl_path,
        )

        def _after(guid, err, _url=url):
            self._url_btn.setEnabled(True)
            if err is None:
                self._url_edit.clear()

        r.done.connect(_after)
        self._submit(r, label=url)

    # ── Qt drop plumbing on the TAB itself (MainWindow delegates here) ─

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        # Forward to the inner drop surface so the UX matches an explicit
        # drop on the big zone.
        self._drop_surface.dropEvent(event)

    # ── internals ──────────────────────────────────────────────────────

    def _on_folder_clicked(self) -> None:
        from ui.import_folder_dialog import ImportFolderDialog

        dlg = ImportFolderDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        folder = dlg.chosen_folder()
        if folder is None:
            return
        # ingest_folder is quick per-file (no network); running it inline
        # on the main thread is acceptable for v1.3. A proper worker will
        # come if users report slowness on multi-thousand-file imports.
        max_hours = int(self._ctx.settings.local_max_duration_hours)
        wl_path = self._ctx.data_dir / "watchlist.yaml"
        guids = ingest_folder(
            folder,
            show_slug=dlg.show_slug(),
            state=self._ctx.state,
            watchlist_path=wl_path,
            recursive=dlg.recursive(),
            max_duration_hours=max_hours,
        )
        for g in guids:
            self.ingested.emit(g)

    def _on_url_clicked(self) -> None:
        text = self._url_edit.text().strip()
        if text:
            self.handle_url(text)

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
