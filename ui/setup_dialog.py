"""Guided setup — shown once after the first-run wizard on fresh install.

Three pages:
  1. Transcripts folder (default ~/Desktop/Paragraphos/transcripts).
  2. Obsidian yes/no.
  3. Pick vault + optional co-locate checkbox.

On Finish, writes back to the Settings instance and flips setup_completed.
Does NOT persist to disk — caller does that after exec() returns.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.models import Settings


def _desktop() -> str:
    return str(Path.home() / "Desktop")


def _smart_start_vault() -> str:
    """Prefer ~/Documents if it seems to host Obsidian vaults (any child
    with a .obsidian/ subfolder), else ~/Desktop."""
    docs = Path.home() / "Documents"
    if docs.exists():
        try:
            for child in docs.iterdir():
                if (child / ".obsidian").exists():
                    return str(docs)
        except OSError:
            pass
    return _desktop()


class SetupDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paragraphos — First-time setup")
        self.setModal(True)
        self.resize(560, 440)
        self._settings = settings

        root = QVBoxLayout(self)
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_output_page())
        self._stack.addWidget(self._build_obsidian_page())
        self._stack.addWidget(self._build_vault_page())
        root.addWidget(self._stack, 1)

        # Footer with Back/Next/Finish — rendered per-page dynamically below.
        self._footer = QHBoxLayout()
        self._back_btn = QPushButton("Back")
        self._back_btn.clicked.connect(self._on_back)
        self._next_btn = QPushButton("Next")
        self._next_btn.clicked.connect(self._on_next)
        self._finish_btn = QPushButton("Finish")
        self._finish_btn.setDefault(True)
        self._finish_btn.clicked.connect(self._finish)
        self._footer.addStretch(1)
        self._footer.addWidget(self._back_btn)
        self._footer.addWidget(self._next_btn)
        self._footer.addWidget(self._finish_btn)
        root.addLayout(self._footer)
        self._sync_footer()

    # ── Page 1: output folder ──
    def _build_output_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("<h3>Where should transcripts be saved?</h3>"))
        v.addWidget(QLabel("Each show gets its own subfolder inside this path."))
        row = QHBoxLayout()
        self._output_edit = QLineEdit(
            self._settings.output_root or f"{_desktop()}/Paragraphos/transcripts"
        )
        row.addWidget(self._output_edit, 1)
        pick = QPushButton("Choose folder…")
        pick.clicked.connect(self._pick_output)
        row.addWidget(pick)
        v.addLayout(row)
        self._output_preview = QLabel("")
        v.addWidget(self._output_preview)
        v.addStretch(1)
        self._output_edit.textChanged.connect(self._refresh_output_preview)
        self._refresh_output_preview()
        return page

    def _refresh_output_preview(self) -> None:
        path = self._output_edit.text()
        self._output_preview.setText(
            f"<span style='color:#888'>Files will be written as "
            f"<code>{path}/&lt;show-slug&gt;/&lt;episode&gt;.md</code></span>"
        )

    def _pick_output(self) -> None:
        cur = self._output_edit.text()
        start = cur if cur and Path(cur).expanduser().exists() else _desktop()
        d = QFileDialog.getExistingDirectory(self, "Transcripts folder", start)
        if d:
            self._output_edit.setText(d)

    # ── Page 2: Obsidian yes/no ──
    def _build_obsidian_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("<h3>Do you use Obsidian?</h3>"))
        v.addWidget(
            QLabel(
                "Obsidian users can have transcripts written inside their vault so the notes "
                "appear alongside the rest of their knowledge base."
            )
        )
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        self._yes_obsidian_btn = QRadioButton("Yes — I use Obsidian")
        self._no_obsidian_btn = QRadioButton("No — plain folders only")
        self._no_obsidian_btn.setChecked(True)
        grp.addButton(self._yes_obsidian_btn)
        grp.addButton(self._no_obsidian_btn)
        v.addWidget(self._yes_obsidian_btn)
        v.addWidget(self._no_obsidian_btn)
        v.addStretch(1)
        # Reactive Next/Finish label flip via sync on selection change.
        grp.buttonToggled.connect(lambda *_: self._sync_footer())
        return page

    # ── Page 3: vault pick ──
    def _build_vault_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.addWidget(QLabel("<h3>Pick your Obsidian vault folder</h3>"))
        row = QHBoxLayout()
        self._vault_edit = QLineEdit("")
        row.addWidget(self._vault_edit, 1)
        pick = QPushButton("Choose vault…")
        pick.clicked.connect(self._pick_vault)
        row.addWidget(pick)
        v.addLayout(row)
        self._vault_status = QLabel("")
        v.addWidget(self._vault_status)
        self._vault_colocate = QCheckBox(
            "Put transcripts inside the vault at <vault>/raw/transcripts"
        )
        self._vault_colocate.setChecked(True)
        v.addWidget(self._vault_colocate)
        v.addStretch(1)
        self._vault_edit.textChanged.connect(self._refresh_vault_status)
        return page

    def _pick_vault(self) -> None:
        cur = self._vault_edit.text()
        start = cur if cur and Path(cur).expanduser().exists() else _smart_start_vault()
        d = QFileDialog.getExistingDirectory(self, "Obsidian vault", start)
        if d:
            self._vault_edit.setText(d)

    def _refresh_vault_status(self) -> None:
        p = Path(self._vault_edit.text()).expanduser() if self._vault_edit.text() else None
        if p is None or not p.exists():
            self._vault_status.setText("")
            return
        if (p / ".obsidian").exists():
            self._vault_status.setText(
                f"<span style='color:#3a7a3a'>Detected Obsidian vault: <b>{p.name}</b></span>"
            )
        else:
            self._vault_status.setText(
                "<span style='color:#b88436'>No .obsidian folder found — "
                "this looks like a regular folder.</span>"
            )

    # ── Footer / navigation ──
    def _sync_footer(self) -> None:
        idx = self._stack.currentIndex()
        self._back_btn.setEnabled(idx > 0)
        # On the Obsidian-yes/no page and the output page, 'Next' is shown;
        # Finish only on the last applicable page.
        on_last = idx == 2 or (idx == 1 and self._no_obsidian_btn.isChecked())
        self._next_btn.setVisible(not on_last)
        self._finish_btn.setVisible(on_last)

    def _on_back(self) -> None:
        self._stack.setCurrentIndex(max(0, self._stack.currentIndex() - 1))
        self._sync_footer()

    def _on_next(self) -> None:
        self._stack.setCurrentIndex(min(2, self._stack.currentIndex() + 1))
        self._sync_footer()

    def _finish(self) -> None:
        # Persist choices to the Settings instance. Caller saves to disk.
        self._settings.output_root = self._output_edit.text().strip()
        if self._yes_obsidian_btn.isChecked():
            vault = self._vault_edit.text().strip()
            self._settings.obsidian_vault_path = vault
            if vault:
                self._settings.obsidian_vault_name = Path(vault).name
                if self._vault_colocate.isChecked():
                    self._settings.output_root = str(Path(vault) / "raw" / "transcripts")
        else:
            # Clear any legacy vault so the main-window banner correctly
            # treats this user as plain-folders.
            self._settings.obsidian_vault_path = ""
            self._settings.obsidian_vault_name = ""
        self._settings.setup_completed = True
        self.accept()


def show_setup_if_needed(settings: Settings, parent=None) -> bool:
    """Return True when the caller should proceed to the main window.

    If setup is already completed, returns immediately. Otherwise shows
    the dialog; caller is responsible for persisting Settings on True.
    Dialog can be cancelled (close button) — returns True regardless so
    the user isn't locked out; next run will re-prompt because
    ``setup_completed`` stays False."""
    if settings.setup_completed:
        return True
    dlg = SetupDialog(settings, parent)
    dlg.exec()
    return True
