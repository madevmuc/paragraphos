"""Shared helpers for bumping an episode's queue priority.

Used by the Queue tab and the Show Details recent-episodes table so both
menus share the same set of priority values. The worker thread orders its
pending-query by `priority DESC, pub_date`, so bumping priority makes an
episode jump ahead without re-transcribing it.
"""

from __future__ import annotations

# Priority values — kept in sync with `ui.retranscribe` which uses 10 as
# the "run now" level for re-transcribes.
PRIORITY_RUN_NEXT = 5
PRIORITY_RUN_NOW = 10

# Statuses where a priority bump is still meaningful — anything past
# `downloading` has already left the queue stage so bumping is pointless.
BUMPABLE_STATUSES = frozenset({"pending", "downloading"})


def can_bump(status: str | None) -> bool:
    """True iff an episode in this status can still be reordered by priority."""
    return (status or "").lower() in BUMPABLE_STATUSES


def bump_priority(ctx, guid: str, priority: int) -> None:
    """Set `priority` on the given episode via the shared state DB."""
    ctx.state.set_priority(guid, priority)
