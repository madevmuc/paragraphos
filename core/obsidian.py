"""Discover Obsidian vaults on the local filesystem.

A vault is any directory that contains an `.obsidian/` subdirectory.
We walk a small set of likely roots (Documents, home, iCloud-synced
Obsidian dir, Dropbox) one level deep — Obsidian vaults aren't
typically nested deep, and a recursive scan would be too slow on
heavily-used home dirs.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

_LIKELY_ROOTS = [
    Path.home() / "Documents",
    Path.home(),
    Path.home() / "Library" / "Mobile Documents" / "iCloud~md~obsidian" / "Documents",
    Path.home() / "Dropbox",
]


def is_obsidian_vault(path: Path) -> bool:
    return path.is_dir() and (path / ".obsidian").is_dir()


def discover_vaults(extra_roots: list[Path] | None = None) -> List[Path]:
    """Return every detected vault under the standard roots, deduped.

    Walks each root one level deep (i.e., direct children only). If a root
    itself is a vault, include it.
    """
    roots = list(_LIKELY_ROOTS) + list(extra_roots or [])
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            root = root.expanduser()
        except Exception:  # noqa: BLE001
            continue
        if not root.exists():
            continue
        candidates: list[Path] = []
        if is_obsidian_vault(root):
            candidates.append(root)
        try:
            candidates.extend(p for p in root.iterdir() if is_obsidian_vault(p))
        except (PermissionError, OSError):
            continue
        for c in candidates:
            try:
                cr = c.resolve()
            except OSError:
                continue
            if cr not in seen:
                seen.add(cr)
                found.append(c)
    return found


def best_guess_vault() -> Path | None:
    """Return the first vault found, or None. Used by the setup dialog
    to pre-fill the field on first show."""
    vaults = discover_vaults()
    return vaults[0] if vaults else None
