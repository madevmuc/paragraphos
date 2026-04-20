"""SQLite state store for episodes/jobs/meta."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, Optional


class EpisodeStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    DONE = "done"
    FAILED = "failed"
    STALE = "stale"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    guid TEXT PRIMARY KEY,
    show_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    pub_date TEXT NOT NULL,
    mp3_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    mp3_path TEXT,
    transcript_path TEXT,
    attempted_at TEXT,
    completed_at TEXT,
    error_text TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_show ON episodes(show_slug);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    show_slug TEXT,
    guid TEXT,
    pid INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    error_text TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def init_schema(self) -> None:
        with self._conn() as c:
            # WAL mode lets watchdog, worker thread, and UI refresh all
            # read/write concurrently without file-level locking.
            # synchronous=NORMAL is safe with WAL and significantly
            # faster than the default FULL.
            try:
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA synchronous=NORMAL")
            except Exception:
                pass  # some filesystems don't support WAL — fall back
            c.executescript(_SCHEMA)
            # Idempotent column additions (ignore if they already exist).
            for stmt in (
                "ALTER TABLE episodes ADD COLUMN duration_sec INTEGER",
                "ALTER TABLE episodes ADD COLUMN word_count INTEGER",
                "ALTER TABLE episodes ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
            ):
                try:
                    c.execute(stmt)
                except Exception:
                    pass

    def upsert_episode(self, *, show_slug: str, guid: str, title: str,
                       pub_date: str, mp3_url: str,
                       duration_sec: int | None = None) -> None:
        with self._conn() as c:
            c.execute("""
                INSERT INTO episodes (guid, show_slug, title, pub_date, mp3_url,
                                       status, duration_sec)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(guid) DO UPDATE SET
                    title=excluded.title,
                    pub_date=excluded.pub_date,
                    mp3_url=excluded.mp3_url,
                    duration_sec=COALESCE(excluded.duration_sec, episodes.duration_sec)
            """, (guid, show_slug, title, pub_date, mp3_url, duration_sec))

    def record_completion(self, guid: str, word_count: int,
                          duration_sec: int | None = None) -> None:
        with self._conn() as c:
            if duration_sec is not None:
                c.execute("UPDATE episodes SET word_count=?, duration_sec=? WHERE guid=?",
                          (word_count, duration_sec, guid))
            else:
                c.execute("UPDATE episodes SET word_count=? WHERE guid=?",
                          (word_count, guid))

    def get_episode(self, guid: str) -> Optional[Dict[str, Any]]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM episodes WHERE guid = ?", (guid,)).fetchone()
            return dict(row) if row else None

    def list_by_status(self, show_slug: str, status: EpisodeStatus) -> list[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM episodes WHERE show_slug=? AND status=? "
                "ORDER BY priority DESC, pub_date",
                (show_slug, status.value),
            ).fetchall()
            return [dict(r) for r in rows]

    def set_priority(self, guid: str, priority: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE episodes SET priority=? WHERE guid=?",
                      (priority, guid))

    def set_status(self, guid: str, status: EpisodeStatus,
                   *, error_text: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            if status == EpisodeStatus.DONE:
                c.execute("UPDATE episodes SET status=?, completed_at=?, error_text=NULL WHERE guid=?",
                          (status.value, now, guid))
            elif status in (EpisodeStatus.DOWNLOADING, EpisodeStatus.TRANSCRIBING):
                c.execute("UPDATE episodes SET status=?, attempted_at=? WHERE guid=?",
                          (status.value, now, guid))
            elif status == EpisodeStatus.FAILED:
                c.execute("UPDATE episodes SET status=?, error_text=? WHERE guid=?",
                          (status.value, error_text, guid))
            else:
                c.execute("UPDATE episodes SET status=? WHERE guid=?",
                          (status.value, guid))

    def recover_in_flight(self) -> int:
        """Called on startup: reset downloading/transcribing → pending."""
        with self._conn() as c:
            cur = c.execute(
                "UPDATE episodes SET status='pending' "
                "WHERE status IN ('downloading', 'transcribing')"
            )
            return cur.rowcount

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("""
                INSERT INTO meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """, (key, value))

    def get_meta(self, key: str) -> Optional[str]:
        with self._conn() as c:
            row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
