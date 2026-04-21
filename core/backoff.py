"""Feed backoff: after N consecutive failures, pause the feed for 1/3/7 days.

State lives in meta:
    feed_fail_count:<slug> — int (consecutive failures)
    feed_backoff_until:<slug> — iso timestamp (UTC) when feed may be tried again
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_STAGES_DAYS = (1, 3, 7)  # after 3rd fail → 1 day, 4th → 3, 5th+ → 7
_THRESHOLD = 3


def on_success(state, slug: str) -> None:
    state.set_meta(f"feed_fail_count:{slug}", "0")
    state.set_meta(f"feed_backoff_until:{slug}", "")
    # Record health so the Shows-tab Feed column can render without a
    # separate health sweep.
    state.set_meta(f"feed_health:{slug}", "ok")


def on_failure(state, slug: str) -> int:
    raw = state.get_meta(f"feed_fail_count:{slug}") or "0"
    count = int(raw) + 1
    state.set_meta(f"feed_fail_count:{slug}", str(count))
    if count >= _THRESHOLD:
        stage_idx = min(count - _THRESHOLD, len(_STAGES_DAYS) - 1)
        days = _STAGES_DAYS[stage_idx]
        until = datetime.now(timezone.utc) + timedelta(days=days)
        state.set_meta(f"feed_backoff_until:{slug}", until.isoformat())
    state.set_meta(f"feed_health:{slug}", "fail")
    return count


def in_backoff(state, slug: str) -> bool:
    until = state.get_meta(f"feed_backoff_until:{slug}") or ""
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now(timezone.utc)
    except ValueError:
        return False
