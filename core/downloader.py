"""Resumable MP3 downloader (Content-Length parity check)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from core.http import get_client
from core.security import (
    MAX_MP3_BYTES,
    DownloadTooLargeError,
    is_allowed_audio_content_type,
    safe_url,
)

logger = logging.getLogger(__name__)

# Retry budget for transient network failures. Per attempt we sleep
# RETRY_DELAYS[attempt] before the next try. Total worst-case wait
# on 3 failed attempts is 1+5+20 = 26 seconds before we give up.
RETRY_DELAYS = (1.0, 5.0, 20.0)

# HTTP status codes that deserve a retry. 4xx means the URL is gone
# for good (404 episode pulled, 403 auth-gated, 410 gone) — no point
# hammering it.
RETRIABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRIABLE_STATUSES
    # Timeouts, connection errors, protocol errors, pool errors — all
    # transient. TooLarge / security errors propagate up untouched.
    return isinstance(
        exc,
        (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, httpx.PoolTimeout),
    )


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
    r = get_client().head(
        url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=timeout
    )
    r.raise_for_status()
    return int(r.headers.get("content-length", "0") or 0)


def _head(url: str, timeout: float = 10.0) -> httpx.Response:
    r = get_client().head(
        url, headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=timeout
    )
    r.raise_for_status()
    return r


def download_mp3(
    url: str,
    dest: Path,
    *,
    chunk: int = 1 << 16,
    timeout: float = 60.0,
    max_bytes: int = MAX_MP3_BYTES,
    _sleep=time.sleep,
) -> DownloadResult:
    """Download an MP3 with retry on transient network failures.

    Retries 3×: delays 1s, 5s, 20s. Retries on 5xx / 429 / timeouts /
    network errors. Does NOT retry on 4xx (URL permanently gone),
    DownloadTooLargeError, or safe_url guard violations.
    """
    safe_url(url)
    dest.parent.mkdir(parents=True, exist_ok=True)

    last_exc: BaseException | None = None
    for attempt, delay in enumerate(RETRY_DELAYS):
        try:
            return _download_once(url, dest, chunk=chunk, timeout=timeout, max_bytes=max_bytes)
        except Exception as e:
            if not _should_retry(e):
                raise
            last_exc = e
            logger.warning(
                "download transient failure attempt %d/%d — sleeping %.0fs then retrying: %s",
                attempt + 1,
                len(RETRY_DELAYS),
                delay,
                e,
            )
            _sleep(delay)
    # All retries exhausted.
    assert last_exc is not None
    raise last_exc


def _download_once(
    url: str, dest: Path, *, chunk: int, timeout: float, max_bytes: int
) -> DownloadResult:
    expected = 0
    accept_ranges = False
    try:
        head = _head(url, timeout=timeout)
        expected = int(head.headers.get("content-length", "0") or 0)
        accept_ranges = head.headers.get("accept-ranges", "").lower() == "bytes"
    except httpx.HTTPError:
        pass  # Some servers block HEAD — fall through to GET.
    if expected and expected > max_bytes:
        raise DownloadTooLargeError(
            f"remote advertises {expected} bytes — refusing (cap {max_bytes})"
        )
    if dest.exists() and expected and dest.stat().st_size == expected:
        return DownloadResult(0, True, expected)

    tmp = dest.with_suffix(dest.suffix + ".part")

    # Resume support: if a .part file exists and the server advertises
    # Range support + a known Content-Length, try to continue from the
    # partial offset instead of re-downloading from zero.
    resume_from = 0
    if tmp.exists() and expected and accept_ranges:
        partial_size = tmp.stat().st_size
        if partial_size == expected:
            # Already fully downloaded, just never finalized.
            tmp.replace(dest)
            return DownloadResult(0, True, dest.stat().st_size)
        if partial_size > expected:
            logger.debug(
                "partial %s larger than expected (%d > %d) — discarding",
                tmp,
                partial_size,
                expected,
            )
            tmp.unlink()
        elif 0 < partial_size < expected:
            resume_from = partial_size

    written = 0
    headers: dict[str, str] = {"User-Agent": USER_AGENT}
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"

    with get_client().stream(
        "GET", url, headers=headers, follow_redirects=True, timeout=timeout
    ) as r:
        r.raise_for_status()
        # Content-Type sniff — reject obvious non-audio (HTML, JSON, etc.).
        ct = r.headers.get("content-type", "")
        if ct and not is_allowed_audio_content_type(ct):
            if not ct.lower().startswith("application/octet-stream"):
                raise ValueError(f"refusing non-audio Content-Type: {ct!r}")

        # If we asked for a Range and got 200 back, the server ignored it.
        # Truncate the partial and restart from zero.
        mode = "wb"
        if resume_from:
            if r.status_code == 206:
                mode = "ab"
                written = resume_from
            else:
                logger.debug(
                    "server returned %d to Range request — restarting from zero",
                    r.status_code,
                )
                resume_from = 0

        with tmp.open(mode) as f:
            for block in r.iter_bytes(chunk):
                f.write(block)
                written += len(block)
                if written > max_bytes:
                    f.close()
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                    raise DownloadTooLargeError(f"stream exceeded {max_bytes} bytes without EOF")
    tmp.replace(dest)
    return DownloadResult(written, False, dest.stat().st_size)
