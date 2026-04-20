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

# Model digests follow a Trust-On-First-Use (TOFU) policy.
#
# On the first successful download of a given model, we record the file's
# SHA256 to ~/Library/Application Support/Paragraphos/model_hashes.yaml.
# Every subsequent verification compares against that pinned value. If
# huggingface.co starts serving a different binary (model updated, CDN
# compromise, MITM), we raise loudly — the user decides whether to trust
# the new hash by deleting the pin.
#
# No hard-coded digests: earlier pinned values were made-up placeholders
# that would have caused every non-default model download to fail.


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _model_hashes_path() -> Path:
    """Where the TOFU pin file lives. Lazy import of paths.user_data_dir to
    avoid importing the full UI stack just to compute a hash location."""
    from core.paths import user_data_dir
    return user_data_dir() / "model_hashes.yaml"


def _load_pinned_hashes() -> dict[str, str]:
    import yaml
    p = _model_hashes_path()
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _save_pinned_hashes(pins: dict[str, str]) -> None:
    import yaml
    p = _model_hashes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(pins, sort_keys=True), encoding="utf-8")


def verify_model(path: Path, model_name: str) -> None:
    """Trust-On-First-Use integrity check.

    - First time we see a given `model_name`: record its SHA256.
    - Subsequent calls: compare against the pin; raise ValueError on
      mismatch (the user decides whether to trust the new file by
      deleting the pin from model_hashes.yaml).
    """
    actual = sha256_of(path)
    pins = _load_pinned_hashes()
    expected = pins.get(model_name)
    if expected is None:
        pins[model_name] = actual
        _save_pinned_hashes(pins)
        return
    if actual != expected:
        raise ValueError(
            f"model {model_name!r} SHA256 changed:\n"
            f"  expected (pinned): {expected}\n"
            f"  actual (on disk):  {actual}\n"
            f"If you trust the new file, delete the entry from\n"
            f"  {_model_hashes_path()}\n"
            f"and retry the download.")


# --------------------------------------------------------------------------- #
# Size caps
# --------------------------------------------------------------------------- #

# Be generous — podcasts can be 300 MB+, but cap the worst case.
MAX_MP3_BYTES = 2 * 1024 * 1024 * 1024   # 2 GB
MAX_FEED_BYTES = 50 * 1024 * 1024        # 50 MB
MAX_HTML_BYTES = 10 * 1024 * 1024        # 10 MB


class DownloadTooLargeError(ValueError):
    pass
