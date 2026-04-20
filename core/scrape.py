"""Scrape a podcast episode landing page: MP3 URL, title, show, pub date."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from core.security import MAX_HTML_BYTES, safe_url

USER_AGENT = "paragraphos/0.3"


@dataclass(frozen=True)
class ScrapedEpisode:
    mp3_url: str
    title: str
    show_name: Optional[str]
    pub_date: Optional[str]  # YYYY-MM-DD
    source_url: str


def _is_audio(ct: str) -> bool:
    ct = (ct or "").lower()
    return ct.startswith("audio/") or "mpeg" in ct


def _iso_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def _try_opengraph(soup: BeautifulSoup) -> Optional[ScrapedEpisode]:
    def og(prop: str) -> Optional[str]:
        tag = soup.find("meta", property=prop)
        return tag.get("content") if tag else None

    audio = og("og:audio")
    if not audio:
        return None
    return ScrapedEpisode(
        mp3_url=audio,
        title=og("og:title") or "untitled",
        show_name=og("og:site_name"),
        pub_date=_iso_date(og("article:published_time")),
        source_url="",
    )


def _try_jsonld(soup: BeautifulSoup) -> Optional[ScrapedEpisode]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") != "PodcastEpisode":
                continue
            media = item.get("associatedMedia") or {}
            if isinstance(media, list):
                media = media[0] if media else {}
            content_url = media.get("contentUrl") if isinstance(media, dict) else None
            if not content_url:
                continue
            series = item.get("partOfSeries") or {}
            return ScrapedEpisode(
                mp3_url=content_url,
                title=item.get("name", "untitled"),
                show_name=series.get("name") if isinstance(series, dict) else None,
                pub_date=_iso_date(item.get("datePublished")),
                source_url="",
            )
    return None


def _try_audio_tag(soup: BeautifulSoup) -> Optional[ScrapedEpisode]:
    tag = soup.find("audio")
    if not tag:
        return None
    src = tag.get("src")
    if not src:
        source = tag.find("source")
        src = source.get("src") if source else None
    if not src:
        return None
    title_tag = soup.find("title")
    return ScrapedEpisode(
        mp3_url=src,
        title=(title_tag.text.strip() if title_tag else "untitled"),
        show_name=None,
        pub_date=None,
        source_url="",
    )


def scrape_episode(url: str, *, timeout: float = 10.0) -> ScrapedEpisode:
    safe_url(url)
    # Direct-MP3 detection first — cheap HEAD request.
    try:
        head = httpx.head(url, headers={"User-Agent": USER_AGENT},
                          follow_redirects=True, timeout=timeout)
        if head.status_code < 400 and _is_audio(head.headers.get("content-type", "")):
            name = urlparse(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            return ScrapedEpisode(mp3_url=url, title=name or "audio",
                                  show_name=None, pub_date=None, source_url=url)
    except httpx.HTTPError:
        pass  # fall through

    r = httpx.get(url, headers={"User-Agent": USER_AGENT},
                  follow_redirects=True, timeout=timeout)
    r.raise_for_status()
    # Bound HTML size to protect against parser-bombs.
    if len(r.content) > MAX_HTML_BYTES:
        raise ValueError(f"HTML too large: {len(r.content)} bytes")
    soup = BeautifulSoup(r.text, "lxml")
    for extractor in (_try_opengraph, _try_jsonld, _try_audio_tag):
        ep = extractor(soup)
        if ep:
            # Revalidate the extracted mp3_url — feed might point at file://
            safe_url(ep.mp3_url)
            return ScrapedEpisode(
                mp3_url=ep.mp3_url, title=ep.title, show_name=ep.show_name,
                pub_date=ep.pub_date, source_url=url,
            )
    raise ValueError(f"no audio found at {url}")
