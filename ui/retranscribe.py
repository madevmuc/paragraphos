"""Shared `re-transcribe single episode` action.

Used by the Queue tab context menu and the Show Details dialog's
recent-episodes table. Keeping the logic in one place means both
entry points honor the same .md → .md.bak convention that D3
(diff view) depends on.
"""

from __future__ import annotations

from pathlib import Path

from core.pipeline import build_slug
from core.state import EpisodeStatus


def retranscribe_episode(ctx, guid: str) -> None:
    """Reset an episode to `pending` with bumped priority, backing up any
    existing .md transcript so a diff is possible later.

    Harmless if the episode has never been transcribed — the .md simply
    won't exist and is skipped.
    """
    ep = ctx.state.get_episode(guid)
    if ep is None:
        return

    # Derive the transcript path the same way the pipeline does.
    output_root = Path(ctx.settings.output_root).expanduser()
    slug = build_slug(ep.get("pub_date") or "", ep.get("title") or "", "0000")
    md_path = output_root / ep["show_slug"] / f"{slug}.md"

    if md_path.exists():
        bak = md_path.with_suffix(".md.bak")
        if bak.exists():
            bak.unlink()
        md_path.rename(bak)

    ctx.state.set_status(guid, EpisodeStatus.PENDING)
    ctx.state.set_priority(guid, 10)
