"""Source-filter helpers: which content types the user has enabled.

YouTube ingestion code paths must call `youtube_enabled(settings)` and
no-op when False, so a user who unchecks YouTube in Settings doesn't
trigger yt-dlp installs or see YouTube UI.
"""

from __future__ import annotations

from core.models import Settings


class SourcesError(ValueError):
    """At least one source (podcasts or youtube) must be enabled."""


def podcasts_enabled(s: Settings) -> bool:
    return bool(s.sources_podcasts)


def youtube_enabled(s: Settings) -> bool:
    return bool(s.sources_youtube)


def validate_sources(s: Settings) -> None:
    if not (s.sources_podcasts or s.sources_youtube):
        raise SourcesError("At least one source must be enabled (Podcasts or YouTube).")
