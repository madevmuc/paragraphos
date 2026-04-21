"""Cover-art fetch + disk cache for podcast shows.

Artwork is cached under
``~/Library/Application Support/Paragraphos/artwork/<slug>.<ext>`` so
opening Show Details a second time doesn't re-hit the feed's CDN. The
cache is intentionally write-once-per-URL: we key only on slug, not on a
hash of the URL, because when a show re-publishes artwork the feed URL
usually changes too — and the easiest way to refresh the cached file is
"Refresh from feed" which calls :func:`ensure_artwork` with the new URL,
overwriting the old bytes.

``ensure_artwork`` is network-bound and MUST be called off the UI
thread. The Show Details dialog spins up a short-lived QThread for it
so dialog-open stays snappy even when the CDN is slow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from core.http import get_client
from core.paths import user_data_dir

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# Hard cap per file — podcast artwork is usually 1–2 MB JPEG / PNG.
# Refuse anything larger to keep a pathological CDN from filling the
# cache dir. 8 MiB is well above real-world cover art.
_MAX_BYTES = 8 * 1024 * 1024

# Map Content-Type → extension. Fallback to .img if the server lies.
_CT_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def artwork_dir() -> Path:
    """Cache directory for cover art. Created on first call."""
    d = user_data_dir() / "artwork"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ext_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for suffix in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(suffix):
            return ".jpg" if suffix == ".jpeg" else suffix
    return ""


def _existing_cached(slug: str) -> Optional[Path]:
    d = artwork_dir()
    for ext in (".jpg", ".png", ".webp", ".gif", ".img"):
        p = d / f"{slug}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def ensure_artwork(slug: str, url: str, *, timeout: float = 15.0) -> Optional[Path]:
    """Return a local path to the cached cover art, downloading if needed.

    Returns ``None`` if ``url`` is empty, the fetch fails, or the
    response is unexpectedly large. Safe to call repeatedly — the second
    call is a stat(2), not a network request.

    Never raises for expected failure modes (network errors, oversized
    responses, non-image content): callers are expected to render a
    placeholder in those cases.
    """
    if not url:
        return None
    cached = _existing_cached(slug)
    if cached is not None:
        return cached

    try:
        r = get_client().get(
            url,
            headers={"User-Agent": _USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        )
        r.raise_for_status()
    except Exception:
        return None

    if len(r.content) == 0 or len(r.content) > _MAX_BYTES:
        return None

    ct = (r.headers.get("content-type", "") or "").split(";", 1)[0].strip().lower()
    ext = _CT_EXT.get(ct) or _ext_from_url(url) or ".img"

    out = artwork_dir() / f"{slug}{ext}"
    try:
        out.write_bytes(r.content)
    except OSError:
        return None
    return out
