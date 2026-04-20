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
    output_root: str = "~/dev/knowledge-hub/raw/transcripts"
    daily_check_time: str = "09:00"
    catch_up_missed: bool = True
    notify_on_success: bool = True
    mp3_retention_days: int = 7
    delete_mp3_after_transcribe: bool = True
    bandwidth_limit_mbps: int = 0
    parallel_transcribe: int = 1
    # Block E defaults
    obsidian_vault_path: str = "~/dev/knowledge-hub"
    obsidian_vault_name: str = "knowledge-hub"
    export_root: str = "~/Downloads"
    whisper_model: str = "large-v3-turbo"
    log_retention_days: int = 90

    @field_validator("daily_check_time")
    @classmethod
    def _validate_time(cls, v: str) -> str:
        if not _TIME_RE.match(v):
            raise ValueError(f"invalid HH:MM time: {v!r}")
        return v

    @classmethod
    def load(cls, path: Path) -> "Settings":
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
