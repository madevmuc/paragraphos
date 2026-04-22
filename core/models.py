"""Pydantic models for watchlist.yaml and settings.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Show(BaseModel):
    slug: str
    title: str
    rss: str
    whisper_prompt: str = ""
    enabled: bool = True
    output_override: Optional[str] = None
    language: str = "de"  # whisper language code; "auto" for per-episode detect
    # Cover art URL (from <itunes:image> or <image>) captured at add / refresh
    # time. Default is empty string for backward compat with existing
    # watchlist.yaml files — ShowDetailsDialog falls back to a 🎙 placeholder
    # when the feed didn't expose artwork.
    artwork_url: str = ""


class Watchlist(BaseModel):
    shows: List[Show] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Watchlist":
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.model_dump(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


class Settings(BaseModel):
    output_root: str = "~/Desktop/Paragraphos/transcripts"
    daily_check_time: str = "09:00"
    catch_up_missed: bool = True
    # Auto-start queue when the app launches. On by default so opening
    # Paragraphos begins work immediately; turn off if you prefer the
    # queue to sit idle until you click Start.
    auto_start_queue: bool = True
    notify_on_success: bool = True
    # Flipped True the first time the user completes the first-run setup
    # dialog. Legacy users with customised paths get auto-backfilled on load
    # (see ``backfill_setup_completed``) so the dialog doesn't ambush them.
    setup_completed: bool = False
    mp3_retention_days: int = 7
    delete_mp3_after_transcribe: bool = True
    bandwidth_limit_mbps: int = 0
    parallel_transcribe: int = 1
    # Block E defaults
    obsidian_vault_path: str = ""
    obsidian_vault_name: str = "knowledge-hub"
    export_root: str = "~/Downloads"
    whisper_model: str = "large-v3-turbo"
    log_retention_days: int = 90
    # Performance toggles (Phase 1.5)
    whisper_fast_mode: bool = False  # beam=1/best=1/-ac 0, ~2-3× speedup, lower quality
    whisper_multiproc: int = 1  # whisper-cli -p N file split (1 = off)
    rss_concurrency: int = 8  # parallel feed fetches per check
    download_concurrency: int = 4  # parallel MP3 downloads
    download_concurrency_per_host: int = 2
    use_etag_cache: bool = True  # RSS conditional GET
    library_scan_cache: bool = True  # skip re-parse of unchanged .md at startup
    # Phase 3 UX
    notify_mode: str = "per_episode"  # per_episode | daily_summary | off
    # Optional external knowledge-base root (e.g. an Obsidian vault /
    # knowledge-hub repo). When set AND the directory contains
    # raw/.last_compiled, the Shows tab shows a 'N transcripts since last
    # compile' banner. Empty string disables the banner.
    knowledge_hub_root: str = ""
    github_repo: str = "madevmuc/paragraphos"  # override if you forked
    # Output formats — Markdown is always written; SRT is opt-in. Default
    # True so upgraders see no behaviour change on first launch.
    save_srt: bool = True

    @field_validator("daily_check_time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError(f"invalid HH:MM time: {v!r}")
        return v

    @classmethod
    def load(cls, path: Path) -> "Settings":
        if not path.exists():
            # Fresh install — populate HW-aware tuning defaults so the
            # queue-tab tuning-hint banner doesn't immediately shout at
            # brand-new users. Persist so subsequent loads see the values
            # (which then take the existing-file branch below).
            s = cls()
            _apply_hw_defaults(s)
            try:
                s.save(path)
            except Exception:
                # If we can't persist (e.g. read-only fs in tests), still
                # return the populated in-memory settings.
                pass
            backfill_setup_completed(s)
            return s
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        s = cls.model_validate(data)
        backfill_setup_completed(s)
        return s

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.model_dump(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


def _apply_hw_defaults(s: "Settings") -> None:
    """Populate parallel_transcribe + whisper_multiproc with hardware-
    aware recommendations. Called only on fresh install — saved user
    values are never overwritten."""
    try:
        from core.hw import recommended_multiproc_split, recommended_parallel_workers

        s.parallel_transcribe = recommended_parallel_workers()
        s.whisper_multiproc = recommended_multiproc_split()
    except Exception:
        # HW detect failure — leave generic defaults in place.
        pass


def backfill_setup_completed(s: Settings) -> None:
    """Legacy users had the setup steps implicitly done through manual
    edits — flip the new ``setup_completed`` flag True so the first-run
    setup dialog doesn't ambush them on upgrade.

    Mutates ``s`` in place; returns ``None``."""
    if s.setup_completed:
        return
    defaults = Settings()
    customised = (
        s.output_root != defaults.output_root
        or s.obsidian_vault_path != defaults.obsidian_vault_path
        or s.knowledge_hub_root != defaults.knowledge_hub_root
    )
    if customised:
        s.setup_completed = True
