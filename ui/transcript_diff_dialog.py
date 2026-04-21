"""Side-by-side transcript diff — shown after a re-transcribe."""

from __future__ import annotations

import difflib
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QPushButton, QTextBrowser, QVBoxLayout


class TranscriptDiffDialog(QDialog):
    """Open side-by-side diff of old (.md.bak) vs new (.md) transcripts."""

    def __init__(self, old_path: Path, new_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transcript diff")
        self.resize(900, 600)

        v = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)

        old_lines = old_path.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = new_path.read_text(encoding="utf-8", errors="replace").splitlines()
        html = difflib.HtmlDiff(tabsize=2, wrapcolumn=80).make_table(
            old_lines,
            new_lines,
            fromdesc=old_path.name,
            todesc=new_path.name,
            context=False,
        )
        # Scope-minimal CSS: difflib's output is a complete HTML fragment.
        # Wrap with a font-family + background reset.
        browser.setHtml(
            "<html><head><style>"
            "body { font-family: -apple-system, system-ui, sans-serif; font-size: 12px; }"
            "table.diff { border-collapse: collapse; width: 100%; }"
            ".diff_header { background: palette(alternate-base); }"
            ".diff_add { background: #e6f4ea; }"
            ".diff_chg { background: #fff4ce; }"
            ".diff_sub { background: #fce8e6; }"
            "</style></head><body>" + html + "</body></html>"
        )
        v.addWidget(browser)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        close.setDefault(True)
        v.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
