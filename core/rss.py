"""RSS feed parsing — produces manifests in the project's canonical format.

Canonical manifest entry (matches raw/transcripts/*/episodes.json):

    {
        "guid": str,                     # entry.id, unique
        "title": str,
        "pubDate": "YYYY-MM-DDTHH:MM:SS", # ISO 8601, no tz
        "duration": str,                 # seconds OR HH:MM:SS / MM:SS — preserve feed's format
        "episode_number": str,           # 4-digit zero-padded, "0000" if missing
        "mp3_url": str,
        "description": str,
        "url": str,                      # episode landing page
    }

Array sorted oldest → newest by pubDate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import feedparser
import httpx

from core.security import MAX_FEED_BYTES, safe_url

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


@dataclass
class FeedHealth:
    ok: bool
    reason: str
    canonical_url: Optional[str] = None

    @classmethod
    def check(cls, url: str, *, timeout: float = 10.0) -> "FeedHealth":
        try:
            r = httpx.head(url, headers={"User-Agent": USER_AGENT},
                           follow_redirects=True, timeout=timeout)
        except httpx.HTTPError as e:
            return cls(False, f"network: {e}")
        if r.status_code >= 400:
            return cls(False, f"HTTP {r.status_code}")
        return cls(True, "", canonical_url=str(r.url))


def _extract_mp3_url(entry: Any) -> Optional[str]:
    # Prefer explicit audio/mpeg enclosure
    for link in entry.get("links", []) or []:
        if link.get("type") == "audio/mpeg" or link.get("rel") == "enclosure":
            href = link.get("href")
            if href:
                return href
    for enc in entry.get("enclosures", []) or []:
        t = enc.get("type", "")
        if t.startswith("audio") or not t:
            href = enc.get("href") or enc.get("url")
            if href:
                return href
    return None


def _pub_date_iso(entry: Any) -> str:
    """Return 'YYYY-MM-DDTHH:MM:SS' (no tz) or empty string."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6]).isoformat()
        except (TypeError, ValueError):
            pass
    # Fallback: feedparser gives raw 'published'
    raw = entry.get("published") or entry.get("updated") or ""
    return raw


def _episode_number(entry: Any) -> str:
    ep = entry.get("itunes_episode") or ""
    try:
        return str(int(ep)).zfill(4)
    except (TypeError, ValueError):
        return "0000"


def _duration(entry: Any) -> str:
    d = entry.get("itunes_duration")
    if d is None:
        return "00:00:00"
    return str(d)


def build_manifest(feed_url: str, *, timeout: float = 30.0) -> List[Dict[str, Any]]:
    """Fetch + parse a feed, return the canonical manifest list.

    Network-fetches with our UA then hands text to feedparser. Using httpx up front
    lets us follow redirects and surface real HTTP errors, rather than silently
    receiving feedparser's empty-entries fallback.
    """
    safe_url(feed_url)
    r = httpx.get(feed_url, headers={"User-Agent": USER_AGENT},
                  follow_redirects=True, timeout=timeout)
    r.raise_for_status()
    if len(r.content) > MAX_FEED_BYTES:
        raise ValueError(f"feed too large: {len(r.content)} bytes")
    parsed = feedparser.parse(r.content)

    episodes: List[Dict[str, Any]] = []
    for entry in parsed.entries:
        mp3 = _extract_mp3_url(entry)
        if not mp3:
            continue
        episodes.append({
            "guid": entry.get("id") or entry.get("guid") or mp3,
            "title": entry.get("title", ""),
            "pubDate": _pub_date_iso(entry),
            "duration": _duration(entry),
            "episode_number": _episode_number(entry),
            "mp3_url": mp3,
            "description": entry.get("summary", "") or entry.get("description", ""),
            "url": entry.get("link", ""),
        })

    episodes.sort(key=lambda x: x["pubDate"])
    return episodes


def feed_metadata(feed_url: str, *, timeout: float = 30.0) -> Dict[str, str]:
    """Return channel-level metadata (title, author, description)."""
    r = httpx.get(feed_url, headers={"User-Agent": USER_AGENT},
                  follow_redirects=True, timeout=timeout)
    r.raise_for_status()
    parsed = feedparser.parse(r.content)
    ch = parsed.feed
    return {
        "title": ch.get("title", ""),
        "author": ch.get("author", "") or ch.get("itunes_author", ""),
        "description": ch.get("subtitle", "") or ch.get("description", ""),
        "canonical_url": str(r.url),
    }
