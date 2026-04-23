"""Feed backoff: after N consecutive failures, pause the feed for 1/3/7 days.

State lives in meta:
    feed_fail_count:<slug>     — int (consecutive failures)
    feed_backoff_until:<slug>  — iso timestamp (UTC) when feed may be tried again
    feed_health:<slug>         — "ok" | "fail" (binary; pill colour)
    feed_fail_category:<slug>  — short category from core.feed_errors
                                 (dns / timeout / tls / forbidden / gone /
                                  server / malformed / redirect_loop /
                                  ssrf / too_large / other)
    feed_fail_message:<slug>   — last raw exception text (truncated)
    feed_fail_at:<slug>        — ISO timestamp of last failure
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_STAGES_DAYS = (1, 3, 7)  # after 3rd fail → 1 day, 4th → 3, 5th+ → 7
_THRESHOLD = 3
_MAX_MESSAGE_CHARS = 500


def on_success(state, slug: str) -> None:
    state.set_meta(f"feed_fail_count:{slug}", "0")
    state.set_meta(f"feed_backoff_until:{slug}", "")
    # Record health so the Shows-tab Feed column can render without a
    # separate health sweep. Also clear stale failure detail so the
    # Show-details panel doesn't keep showing yesterday's DNS error.
    state.set_meta(f"feed_health:{slug}", "ok")
    state.set_meta(f"feed_fail_category:{slug}", "")
    state.set_meta(f"feed_fail_message:{slug}", "")
    state.set_meta(f"feed_fail_at:{slug}", "")


def on_failure(state, slug: str, exc: BaseException | None = None) -> int:
    raw = state.get_meta(f"feed_fail_count:{slug}") or "0"
    count = int(raw) + 1
    state.set_meta(f"feed_fail_count:{slug}", str(count))
    if count >= _THRESHOLD:
        stage_idx = min(count - _THRESHOLD, len(_STAGES_DAYS) - 1)
        days = _STAGES_DAYS[stage_idx]
        until = datetime.now(timezone.utc) + timedelta(days=days)
        state.set_meta(f"feed_backoff_until:{slug}", until.isoformat())
    state.set_meta(f"feed_health:{slug}", "fail")
    if exc is not None:
        # Lazy import to avoid a circular dependency: core.feed_errors
        # imports core.security, both of which the rest of core can
        # already import freely.
        from core.feed_errors import categorize

        cat = categorize(exc)
        state.set_meta(f"feed_fail_category:{slug}", cat)
        state.set_meta(f"feed_fail_message:{slug}", str(exc)[:_MAX_MESSAGE_CHARS])
        state.set_meta(f"feed_fail_at:{slug}", datetime.now(timezone.utc).isoformat())
    return count


def in_backoff(state, slug: str) -> bool:
    until = state.get_meta(f"feed_backoff_until:{slug}") or ""
    if not until:
        return False
    try:
        return datetime.fromisoformat(until) > datetime.now(timezone.utc)
    except ValueError:
        return False
