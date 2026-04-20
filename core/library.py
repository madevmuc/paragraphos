"""Library index: scans output_root for existing transcripts, dedup by GUID + filename."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _read_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    m = _FM_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


@dataclass(frozen=True)
class DedupResult:
    matched: bool
    reason: str  # "guid" | "filename" | ""
    path: Optional[Path]


class LibraryIndex:
    """Scans `output_root` for existing transcripts, enables GUID + filename dedup."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._by_guid: Dict[str, Path] = {}
        self._by_filename: Dict[str, Path] = {}

    def scan(self) -> None:
        self._by_guid.clear()
        self._by_filename.clear()
        if not self.root.exists():
            return
        for md in self.root.rglob("*.md"):
            if md.name == "index.md":
                continue
            self._index_one(md)

    def _index_one(self, path: Path) -> None:
        fm = _read_frontmatter(path)
        guid = fm.get("guid")
        if isinstance(guid, str) and guid:
            self._by_guid[guid] = path
        self._by_filename[path.stem] = path

    def add(self, path: Path) -> None:
        self._index_one(path)

    def remove(self, path: Path) -> None:
        self._by_filename.pop(path.stem, None)
        for g, p in list(self._by_guid.items()):
            if p == path:
                self._by_guid.pop(g, None)

    def has_guid(self, guid: str) -> bool:
        return guid in self._by_guid

    def check_dedup(self, *, guid: Optional[str],
                    filename_key: Optional[str]) -> DedupResult:
        if guid and guid in self._by_guid:
            return DedupResult(True, "guid", self._by_guid[guid])
        if filename_key and filename_key in self._by_filename:
            return DedupResult(True, "filename", self._by_filename[filename_key])
        return DedupResult(False, "", None)


def start_watching(idx: LibraryIndex):
    """Start a watchdog observer that keeps the index in sync with the filesystem.

    Returns the observer; caller is responsible for calling .stop()/.join().
    """
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class _Handler(FileSystemEventHandler):
        def __init__(self, target: LibraryIndex):
            self.idx = target

        def _is_md(self, p: str) -> bool:
            return p.endswith(".md") and Path(p).name != "index.md"

        def on_created(self, event):
            if not event.is_directory and self._is_md(event.src_path):
                self.idx.add(Path(event.src_path))

        def on_modified(self, event):
            if not event.is_directory and self._is_md(event.src_path):
                self.idx.add(Path(event.src_path))

        def on_deleted(self, event):
            if not event.is_directory and self._is_md(event.src_path):
                self.idx.remove(Path(event.src_path))

        def on_moved(self, event):
            if event.is_directory:
                return
            if self._is_md(getattr(event, "src_path", "")):
                self.idx.remove(Path(event.src_path))
            if self._is_md(getattr(event, "dest_path", "")):
                self.idx.add(Path(event.dest_path))

    obs = Observer()
    if idx.root.exists():
        obs.schedule(_Handler(idx), str(idx.root), recursive=True)
    obs.start()
    return obs
