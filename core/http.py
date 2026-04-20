"""Module-level httpx.Client with HTTP/2 and keep-alive.

Reusing a single connection pool across the RSS fetch / MP3 download /
HTML scrape callers saves the TLS handshake cost between consecutive
requests to the same host — the 16-show watchlist hits a handful of
CDNs (podigee, buzzsprout, acast, libsyn), so the savings compound.

`http2=True` requires the `h2` extras of httpx. We gate this on
`h2` being importable so the client still works if the dep is absent —
falls back to HTTP/1.1 silently.
"""

from __future__ import annotations

from typing import Optional

import httpx

try:
    import h2  # noqa: F401
    _HTTP2 = True
except ImportError:
    _HTTP2 = False

USER_AGENT = "paragraphos/0.5 (+local podcast transcription)"

_client: Optional[httpx.Client] = None


def get_client() -> httpx.Client:
    global _client
    if _client is None:
        _client = httpx.Client(
            http2=_HTTP2,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=20,
                                max_keepalive_connections=10),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _client


def close_client() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None
