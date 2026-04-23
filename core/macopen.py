"""macOS file-open helpers — single subprocess shell-out per action.

Wraps `open` (the BSD utility) and `osascript` for the "Open With…"
chooser. All paths must be absolute.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def open_default(path: Path) -> None:
    """Open ``path`` with the user's macOS default app for that file
    type. macOS falls back to TextEdit for unknown types so this never
    raises 'no app'."""
    subprocess.run(["open", str(path)], check=False)


def reveal_in_finder(path: Path) -> None:
    """Reveal ``path`` in Finder (parent folder, file selected)."""
    subprocess.run(["open", "-R", str(path)], check=False)


def open_with_chooser(path: Path) -> None:
    """Surface the macOS 'Open With…' chooser sheet, then open the
    file with the chosen application. Uses AppleScript for the picker
    (the only stable cross-version path).
    """
    osa = (
        'set theFile to POSIX file "{p}" as alias\n'
        'set theApp to choose application with prompt "Open " & '
        '(POSIX path of theFile) & " with:" as alias\n'
        'tell application "Finder" to open theFile using theApp'
    ).format(p=str(path).replace('"', '\\"'))
    subprocess.run(["osascript", "-e", osa], check=False)
