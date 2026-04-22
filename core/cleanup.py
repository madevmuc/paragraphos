"""Post-delete file cleanup — preserves user-visible outputs.

The policy: when a user deletes a show or an episode from the
watchlist, remove the recoverable input (the MP3) but keep the
irrecoverable output (the transcript .md and the .srt subtitles).
Re-downloading audio from the feed is free; re-transcribing is not.
"""

from __future__ import annotations

from pathlib import Path


def delete_episode_audio(show_dir: Path, *, basename: str) -> None:
    """Remove only the .mp3 for an episode. Silently ignores missing
    files — cleanup must be idempotent across multiple UI passes."""
    mp3 = show_dir / f"{basename}.mp3"
    if mp3.exists():
        mp3.unlink()


def delete_show_audio(show_dir: Path) -> None:
    """For a whole-show delete: remove every .mp3 in the show folder
    but keep everything else (.md, .srt, assets, etc.). The show
    folder itself is NOT removed."""
    if not show_dir.exists():
        return
    for mp3 in show_dir.glob("*.mp3"):
        mp3.unlink()
