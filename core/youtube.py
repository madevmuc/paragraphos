"""YouTube URL parsing + canonical-RSS helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlparse

YoutubeKind = Literal["video", "channel_id", "handle"]


class YoutubeUrlError(ValueError):
    """URL is not a recognisable YouTube video/channel/handle URL."""


@dataclass(frozen=True)
class YoutubeUrl:
    kind: YoutubeKind
    value: str  # video id, channel id, or handle (without @)


_VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")


def parse_youtube_url(url: str) -> YoutubeUrl:
    u = urlparse(url.strip())
    host = (u.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = u.path or ""

    if host == "youtu.be":
        vid = path.lstrip("/").split("/", 1)[0]
        if _VIDEO_ID_RE.match(vid):
            return YoutubeUrl("video", vid)
        raise YoutubeUrlError(f"bad video id: {vid!r}")

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if path.startswith("/watch"):
            qs = parse_qs(u.query)
            v = (qs.get("v") or [""])[0]
            if _VIDEO_ID_RE.match(v):
                return YoutubeUrl("video", v)
            raise YoutubeUrlError(f"bad video id in query: {v!r}")
        if path.startswith("/channel/"):
            cid = path.split("/", 2)[2].split("/", 1)[0]
            if _CHANNEL_ID_RE.match(cid):
                return YoutubeUrl("channel_id", cid)
            raise YoutubeUrlError(f"bad channel id: {cid!r}")
        if path.startswith("/@"):
            handle = path[2:].split("/", 1)[0]
            if handle:
                return YoutubeUrl("handle", handle)

    raise YoutubeUrlError(f"unrecognised YouTube URL: {url!r}")


def rss_url_for_channel_id(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
