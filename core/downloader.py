"""Resumable MP3 downloader (Content-Length parity check)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from core.security import (DownloadTooLargeError, MAX_MP3_BYTES,
                           is_allowed_audio_content_type, safe_url)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


@dataclass(frozen=True)
class DownloadResult:
    bytes_written: int
    skipped: bool
    final_size: int


def _expected_size(url: str, timeout: float = 10.0) -> int:
    r = httpx.head(url, headers={"User-Agent": USER_AGENT},
                   follow_redirects=True, timeout=timeout)
    r.raise_for_status()
    return int(r.headers.get("content-length", "0") or 0)


def download_mp3(url: str, dest: Path, *, chunk: int = 1 << 16,
                 timeout: float = 60.0,
                 max_bytes: int = MAX_MP3_BYTES) -> DownloadResult:
    safe_url(url)  # raises on file://, data:, localhost, etc.
    dest.parent.mkdir(parents=True, exist_ok=True)
    expected = 0
    try:
        expected = _expected_size(url, timeout=timeout)
    except httpx.HTTPError:
        pass  # Some servers block HEAD — fall through to GET.
    if expected and expected > max_bytes:
        raise DownloadTooLargeError(
            f"remote advertises {expected} bytes — refusing "
            f"(cap {max_bytes})")
    if dest.exists() and expected and dest.stat().st_size == expected:
        return DownloadResult(0, True, expected)

    tmp = dest.with_suffix(dest.suffix + ".part")
    written = 0
    with httpx.stream("GET", url, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True, timeout=timeout) as r:
        r.raise_for_status()
        # Content-Type sniff — reject obvious non-audio (HTML, JSON, etc.)
        # so a compromised feed can't trick us into writing a browser exploit
        # blob under <slug>.mp3.
        ct = r.headers.get("content-type", "")
        if ct and not is_allowed_audio_content_type(ct):
            # Some legitimate CDNs serve MP3 as application/octet-stream —
            # allow that explicitly.
            if not ct.lower().startswith("application/octet-stream"):
                raise ValueError(f"refusing non-audio Content-Type: {ct!r}")
        with tmp.open("wb") as f:
            for block in r.iter_bytes(chunk):
                f.write(block)
                written += len(block)
                if written > max_bytes:
                    f.close()
                    try: tmp.unlink()
                    except OSError: pass
                    raise DownloadTooLargeError(
                        f"stream exceeded {max_bytes} bytes without EOF")
    tmp.replace(dest)
    return DownloadResult(written, False, dest.stat().st_size)
