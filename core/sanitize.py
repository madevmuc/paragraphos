"""Filename sanitizer that preserves Umlauts but strips FS-incompatible chars."""

from __future__ import annotations

import re
import unicodedata

_FORBIDDEN = re.compile(r'[/\\:*?"<>|]')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


def sanitize_filename(name: str, max_bytes: int = 200) -> str:
    """Return a filename that's safe on macOS/APFS while keeping Umlauts/ß.

    Also neutralises path-traversal patterns ('..', path separators) so a
    malicious RSS feed can't use an episode title to write outside the
    show's output directory.
    """
    if not name:
        return "_"
    s = unicodedata.normalize("NFC", name)
    s = _FORBIDDEN.sub("", s)
    s = _CONTROL.sub("", s)
    # Neutralise '..' — after forbidden-char stripping, two consecutive dots
    # remain harmless in the middle of a name but must never appear as the
    # whole/leading component.
    s = s.replace("..", ".")
    s = _WHITESPACE.sub(" ", s)
    s = s.strip(" .")
    if not s:
        return "_"
    encoded = s.encode("utf-8")
    if len(encoded) > max_bytes:
        s = encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()
    return s or "_"
