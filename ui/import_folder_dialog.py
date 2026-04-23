"""Folder-import dialog for the v1.3 universal-ingest feature.

One-shot scan of a chosen directory; queues every recognised media file
under a synthetic show whose slug is either user-supplied or the folder
basename.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.local_source import _MEDIA_EXTS


class ImportFolderDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import folder")
        self._folder: Path | None = None
        self._build()

    # ── exposed for wiring and tests ────────────────────────────────────

    def chosen_folder(self) -> Path | None:
        return self._folder

    def show_slug(self) -> str | None:
        s = self._slug_edit.text().strip()
        return s or None

    def recursive(self) -> bool:
        return self._recurse.isChecked()

    # ── internals ───────────────────────────────────────────────────────

    def _build(self) -> None:
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        self._path_label = QLabel("(no folder chosen)")
        pick = QPushButton("Choose folder…")
        pick.clicked.connect(self._pick)
        row.addWidget(self._path_label, 1)
        row.addWidget(pick)
        root.addLayout(row)

        form = QFormLayout()
        self._slug_edit = QLineEdit()
        self._slug_edit.setPlaceholderText("(defaults to folder name)")
        form.addRow("Show slug:", self._slug_edit)
        self._recurse = QCheckBox("Recurse into subfolders")
        self._recurse.setChecked(True)
        form.addRow(self._recurse)
        root.addLayout(form)

        self._preview = QLabel("")
        self._preview.setStyleSheet("color: palette(mid);")
        root.addWidget(self._preview)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Import")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._recurse.stateChanged.connect(self._refresh_preview)

    def _pick(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Choose folder")
        if p:
            self._folder = Path(p)
            self._path_label.setText(str(self._folder))
            self._slug_edit.setPlaceholderText(self._folder.name)
            self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._folder is None:
            return
        n = self._count_supported(self._folder, recursive=self._recurse.isChecked())
        self._preview.setText(f"Found {n} supported file{'s' if n != 1 else ''}")

    @staticmethod
    def _count_supported(folder: Path, *, recursive: bool) -> int:
        it = folder.rglob("*") if recursive else folder.iterdir()
        return sum(1 for p in it if p.is_file() and p.suffix.lower() in _MEDIA_EXTS)
