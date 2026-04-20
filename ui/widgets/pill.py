"""Styled badge — `Pill(text, kind='ok'|'running'|'fail'|'idle')`.

Object-name / property-based QSS so the `_tokens.py` stylesheet picks
the variant. Size, radius, and text-styling come from the stylesheet;
this class just binds data.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel


class Pill(QLabel):
    ALLOWED_KINDS = ("ok", "fail", "running", "idle")

    def __init__(self, text: str = "", kind: str = "idle", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        if kind not in self.ALLOWED_KINDS:
            kind = "idle"
        self.setProperty("kind", kind)
        # Force style re-compute after property change.
        self.style().unpolish(self)
        self.style().polish(self)
