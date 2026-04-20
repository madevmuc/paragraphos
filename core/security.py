"""Central security helpers: URL validation, path traversal, model checksums.

Paragraphos ingests fully untrusted data: RSS feed XML, HTML landing pages,
and arbitrary MP3 URLs. These helpers harden the boundary so a malicious
feed cannot:

  * read local files via 'file://' / 'data:' scheme injection (SSRF)
  * pivot to private-network hosts via localhost / RFC1918 addresses (SSRF)
  * exhaust disk with an unbounded stream
  * escape the configured output_root with '..' traversal
  * substitute a malicious whisper model via a MITM
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# URL safety
# --------------------------------------------------------------------------- #

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Any content-type that isn't one of these → treat as non-audio.
ALLOWED_AUDIO_CT_PREFIXES = (
    "audio/",
    "application/ogg",
)


class UnsafeURLError(ValueError):
    """Raised when a URL points at something we refuse to fetch."""


def _is_private_ip(host: str) -> bool:
    """True if `host` resolves to a loopback / link-local / private-range IP."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unknown host — downstream httpx will fail cleanly; don't block here
        # because this is called BEFORE we know if the feed exists at all.
        return False
    for family, _type, _proto, _canon, sockaddr in infos:
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return True
    return False


def safe_url(url: str, *, allow_private: bool = False) -> str:
    """Return `url` unchanged if it's safe to fetch, otherwise raise.

    Safe means:
      * scheme is http or https (never file://, data:, javascript:, …)
      * host is present and not obviously a private-network target

    Set `allow_private=True` for callers that legitimately target localhost
    (developer debugging, which we don't currently do).
    """
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("empty URL")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(
            f"refused scheme {parsed.scheme!r} — only http/https allowed")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no host")
    if not allow_private and _is_private_ip(parsed.hostname):
        raise UnsafeURLError(
            f"refused private-network host {parsed.hostname!r} (SSRF guard)")
    return url


def is_allowed_audio_content_type(ct: str) -> bool:
    ct = (ct or "").lower().split(";", 1)[0].strip()
    return any(ct.startswith(p) for p in ALLOWED_AUDIO_CT_PREFIXES)


# --------------------------------------------------------------------------- #
# Path traversal
# --------------------------------------------------------------------------- #

class PathEscapeError(ValueError):
    """Raised when a target path would escape an allowed root directory."""


def safe_path_within(root: Path, target: Path) -> Path:
    """Return resolved `target` if it lies inside `root`, else raise.

    Paragraphos writes `.md` and `.srt` files under `<output_root>/<slug>/`.
    A malicious RSS feed that sets an episode title with embedded '..'
    segments must not be able to write outside that tree.

    Uses `Path.resolve(strict=False)` so the target doesn't need to exist yet.
    """
    root = Path(root).expanduser().resolve()
    target = Path(target).expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError as e:
        raise PathEscapeError(
            f"{target} is outside {root}") from e
    return target


# --------------------------------------------------------------------------- #
# Model integrity
# --------------------------------------------------------------------------- #

# Canonical SHA256 digests of the GGML models we distribute via
# model_download.py. Sourced from huggingface.co/ggerganov/whisper.cpp
# (verify at https://huggingface.co/ggerganov/whisper.cpp/blob/main/<file>).
# If a digest is None we accept the download unverified — better than
# rejecting a genuine but newly-published model. Fill in as they stabilize.
MODEL_SHA256: dict[str, Optional[str]] = {
    # Values pinned from HF on 2026-04-20. Update when huggingface publishes
    # a new revision.
    "base":            "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
    "small":           "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
    "medium":          "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
    "large-v3":        "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
    "large-v3-turbo":  "01bf15bedffe9f39d65c1b6ff9b687ea91f59f0e4eaf9175ab0f0cce2b4312dc",
}


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def verify_model(path: Path, model_name: str) -> None:
    """Raise ValueError if the file's SHA256 doesn't match the pinned digest."""
    expected = MODEL_SHA256.get(model_name)
    if expected is None:
        # Unknown model — skip (don't block), but log upstream.
        return
    actual = sha256_of(path)
    if actual != expected:
        raise ValueError(
            f"model {model_name!r} failed SHA256 check: "
            f"expected {expected}, got {actual}")


# --------------------------------------------------------------------------- #
# Size caps
# --------------------------------------------------------------------------- #

# Be generous — podcasts can be 300 MB+, but cap the worst case.
MAX_MP3_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB
MAX_FEED_BYTES = 50 * 1024 * 1024        # 50 MB
MAX_HTML_BYTES = 10 * 1024 * 1024        # 10 MB


class DownloadTooLargeError(ValueError):
    pass
