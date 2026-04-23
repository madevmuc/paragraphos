"""Categorise feed-fetch failures so the UI can show *why* a feed is
sad and what the user can do about it.

`build_manifest_with_url` raises a small zoo of exception types from
httpx, ssl, socket, the SSRF guard, and feedparser. The Shows table
pill, the Show-details "Feed health" panel, and the CLI all need a
short human-readable bucket plus a fix suggestion. This module is the
single place that does the bucketing.
"""

from __future__ import annotations

# Stable category strings (also persisted to meta so the UI can render
# pills + tooltips without re-deriving). Keep these short — they're
# rendered next to the word "fail" in a 90-px pill.
DNS = "dns"
TIMEOUT = "timeout"
TLS = "tls"
FORBIDDEN = "forbidden"
GONE = "gone"
SERVER = "server"
MALFORMED = "malformed"
REDIRECT_LOOP = "redirect_loop"
SSRF = "ssrf"
TOO_LARGE = "too_large"
OTHER = "other"

ALL_CATEGORIES = (
    DNS,
    TIMEOUT,
    TLS,
    FORBIDDEN,
    GONE,
    SERVER,
    MALFORMED,
    REDIRECT_LOOP,
    SSRF,
    TOO_LARGE,
    OTHER,
)


def categorize(exc: BaseException) -> str:
    """Bucket an exception raised by ``build_manifest_with_url`` (or its
    callers) into one of the stable category strings above. Defaults to
    ``OTHER`` so an unfamiliar exception still gets a known label."""
    name = type(exc).__name__
    msg = str(exc).lower()

    # SSRF guard fires before any network I/O — its own subclass of
    # ValueError. Catch by class first to avoid the generic ValueError
    # branch below misclassifying it.
    from core.security import UnsafeURLError

    if isinstance(exc, UnsafeURLError):
        return SSRF

    # HTTP status errors (httpx.HTTPStatusError carries a response).
    resp = getattr(exc, "response", None)
    status = getattr(resp, "status_code", None)
    if status is not None:
        if status in (404, 410):
            return GONE
        if status in (401, 403):
            return FORBIDDEN
        if 500 <= status <= 599:
            return SERVER
        # 4xx other than the above (e.g. 429 rate limit) → server bucket
        # because they're usually transient publisher-side problems.
        if 400 <= status <= 499:
            return SERVER

    # Class-name pattern matches first (httpx classes don't all inherit
    # from a single timeout/transport base in a way we can isinstance
    # against without importing httpx unconditionally).
    if "Timeout" in name or "timeout" in msg:
        return TIMEOUT
    if name == "TooManyRedirects" or "too many redirects" in msg:
        return REDIRECT_LOOP

    # SSL / TLS — ssl.SSLError, ssl.SSLCertVerificationError, or httpx
    # wrappers carrying "ssl" / "certificate" / "handshake" in the msg.
    if "ssl" in name.lower() or "certificate" in msg or "handshake" in msg or "tls" in msg:
        return TLS

    # DNS / connect errors. ``socket.gaierror`` is the canonical one;
    # httpx wraps it as ConnectError with "Name or service not known"
    # / "[Errno 8]" / "nodename nor servname".
    if name in ("gaierror", "EAI_NONAME") or "name or service not known" in msg:
        return DNS
    if "nodename nor servname" in msg or "name resolution" in msg:
        return DNS

    # Generic transport / connection errors → DNS-ish bucket because
    # for a podcast feed they almost always mean the host is
    # unreachable (offline, DNS, or network).
    if name in ("ConnectError", "ConnectionError", "RemoteProtocolError"):
        return DNS

    # ValueError raised inside build_manifest_with_url for "feed too large".
    if name == "ValueError" and "feed too large" in msg:
        return TOO_LARGE

    # Feedparser / XML parse problems. The rss helpers don't raise these
    # directly today (feedparser swallows into bozo) but downstream
    # callers might still propagate ParseError.
    if "parse" in name.lower() or "xml" in msg or "malformed" in msg:
        return MALFORMED

    return OTHER


_RECOMMENDATIONS: dict[str, str] = {
    DNS: "Host is unreachable — likely DNS or offline. Check your "
    "internet connection. Usually transient; retry in a minute.",
    TIMEOUT: "Feed server is slow or hanging. Often transient — retry "
    "in a few minutes. If it persists, contact the publisher.",
    TLS: "TLS handshake failed. Could be an out-of-date macOS, a "
    "broken corporate MITM proxy, or a publisher with an expired "
    "certificate. Try opening the feed URL in your browser to "
    "confirm.",
    FORBIDDEN: "The feed refused us (HTTP 401/403). The feed may have "
    "moved behind authentication, become geo-blocked, or started "
    "rejecting our User-Agent. Open the URL in a browser to check.",
    GONE: "The feed is dead (HTTP 404/410). The publisher most likely "
    "moved or removed it. Find the new URL on the show's website "
    "and update via Show Details, or remove the show.",
    SERVER: "The feed server returned an error (HTTP 5xx / 4xx). "
    "Usually transient — wait a few hours and retry.",
    MALFORMED: "Feed XML is broken. Often a one-off publisher bug — "
    "retry. If persistent, contact the publisher.",
    REDIRECT_LOOP: "The feed redirects in a loop. Usually a publisher "
    "misconfiguration; report to the publisher.",
    SSRF: "Our safety guard refused the host because it resolves to a "
    "private-network IP. If you believe this is a public host, this "
    "is a bug — please report it with the feed URL.",
    TOO_LARGE: "The feed is larger than our 50 MB safety cap. Usually "
    "a runaway publisher; report to them.",
    OTHER: "Unknown feed-fetch error — see message text. Retry; if it "
    "persists, file a bug with the message + feed URL.",
}


def recommendation(category: str) -> str:
    """Short human-readable next step for a category. Falls back to the
    OTHER bucket text for unknown categories so the UI never renders
    blank."""
    return _RECOMMENDATIONS.get(category, _RECOMMENDATIONS[OTHER])


def label(category: str) -> str:
    """Pretty short label for the category — what the pill shows after
    'fail · '. Defaults to the raw category string."""
    return {
        DNS: "DNS",
        TIMEOUT: "timeout",
        TLS: "TLS",
        FORBIDDEN: "forbidden",
        GONE: "gone",
        SERVER: "server",
        MALFORMED: "malformed",
        REDIRECT_LOOP: "redirect-loop",
        SSRF: "blocked",
        TOO_LARGE: "too large",
        OTHER: "error",
    }.get(category, category)
