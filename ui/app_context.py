"""Shared app state container."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.library import LibraryIndex, start_watching
from core.models import Settings, Watchlist
from core.state import StateStore


@dataclass
class QueueRunState:
    """Live state of the currently running check — shared across all tabs."""

    running: bool = False
    total: int = 0
    done: int = 0
    started_at: Optional[datetime] = None
    avg_sec_per_episode: float = 0.0  # rolling live average (last 10 eps)
    historical_avg_sec: float = 0.0  # fallback before 1st live episode
    last_episode_title: str = ""
    last_episode_show: str = ""

    @property
    def effective_avg_sec(self) -> float:
        """Best available estimate per episode — live rolling avg if we have
        one, historical DB average otherwise."""
        return self.avg_sec_per_episode or self.historical_avg_sec


@dataclass
class AppContext:
    data_dir: Path
    settings: Settings
    watchlist: Watchlist
    state: StateStore
    library: LibraryIndex
    queue: QueueRunState = None  # type: ignore[assignment]
    _observer: object = None

    @classmethod
    def load(cls, data_dir: Path) -> "AppContext":
        settings = Settings.load(data_dir / "settings.yaml")
        watchlist = Watchlist.load(data_dir / "watchlist.yaml")
        state = StateStore(data_dir / "state.sqlite")
        state.init_schema()
        state.recover_in_flight()
        cache_path = data_dir / "library_cache.json" if settings.library_scan_cache else None
        library = LibraryIndex(Path(settings.output_root).expanduser(), cache_path=cache_path)
        library.scan()
        observer = start_watching(library)
        return cls(
            data_dir, settings, watchlist, state, library, queue=QueueRunState(), _observer=observer
        )

    def reload_library(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
        cache_path = (
            self.data_dir / "library_cache.json" if self.settings.library_scan_cache else None
        )
        self.library = LibraryIndex(
            Path(self.settings.output_root).expanduser(), cache_path=cache_path
        )
        self.library.scan()
        self._observer = start_watching(self.library)
