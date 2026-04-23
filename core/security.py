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
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# URL safety
# --------------------------------------------------------------------------- #

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Any content-type that isn't one of these → treat as non-audio.
ALLOWED_AUDIO_CT_PREFIXES = (
    "audio/",
    "application/ogg",
    "application/octet-stream",
    "binary/octet-stream",
)


# Magic bytes for common audio container formats. Used by the downloader
# AFTER the first chunk is read to confirm an octet-stream response is
# actually audio, not e.g. HTML mistakenly served as binary.
def looks_like_audio(first_bytes: bytes) -> bool:
    """Return True if the leading bytes match a known audio magic.

    Recognised: ID3 (tagged MP3), MPEG audio frame sync, fLaC (FLAC),
    OggS (Vorbis/Opus), RIFF (WAV), 'ftyp' inside MP4 box.
    """
    if not first_bytes:
        return False
    head = first_bytes[:12]
    if head.startswith(b"ID3"):
        return True
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return True  # MPEG audio frame sync
    if head.startswith(b"fLaC") or head.startswith(b"OggS"):
        return True
    if head.startswith(b"RIFF"):
        return True
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True  # MP4 / M4A box
    return False


class UnsafeURLError(ValueError):
    """Raised when a URL points at something we refuse to fetch."""


# NAT64 well-known prefixes (RFC 6052 + RFC 8215). macOS's resolver
# synthesises addresses in these ranges for IPv4-only hosts when the
# user is on an IPv6-only / NAT64 network, and Python's ``ipaddress``
# classifies them as ``is_reserved=True`` (IANA's "IPv4/IPv6
# Translators" registration). Without unwrapping the embedded IPv4,
# every public host on a NAT64 LAN would trip the SSRF guard.
_NAT64_WKP = ipaddress.IPv6Network("64:ff9b::/96")
_NAT64_LOCAL = ipaddress.IPv6Network("64:ff9b:1::/48")


def _unwrap_nat64(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """If ``ip`` is in a standardised NAT64 prefix, return the embedded
    IPv4 (last 32 bits per RFC 6052 §2.2 for /96 prefixes). Otherwise
    return ``None``."""
    if ip in _NAT64_WKP or ip in _NAT64_LOCAL:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


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
        # Unwrap IPv4-mapped IPv6 (``::ffff:x.x.x.x`` per RFC 4291) and
        # NAT64-synthesised IPv6 (``64:ff9b::/96`` per RFC 6052). Both
        # appear naturally on macOS when DNS64 / Happy Eyeballs is
        # active, and Python's ``ipaddress`` flags them as
        # ``is_reserved=True``. Without these unwraps, plain public
        # podcast hosts intermittently fail SSRF screening with a
        # misleading "private-network host" error.
        if isinstance(ip, ipaddress.IPv6Address):
            v4 = ip.ipv4_mapped or _unwrap_nat64(ip)
            if v4 is not None:
                ip = v4
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
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
        raise UnsafeURLError(f"refused scheme {parsed.scheme!r} — only http/https allowed")
    if not parsed.hostname:
        raise UnsafeURLError("URL has no host")
    if not allow_private and _is_private_ip(parsed.hostname):
        raise UnsafeURLError(f"refused private-network host {parsed.hostname!r} (SSRF guard)")
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
        raise PathEscapeError(f"{target} is outside {root}") from e
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
    """Backward-compatible loader: returns {model_name: sha256}.

    On-disk entries may be either a bare SHA-256 string (legacy schema) or
    a mapping ``{sha256: <hex>, size: <int>}`` (new schema). Both shapes
    normalize to a string-to-string dict here so existing callers keep
    working. Use :func:`_load_pinned_entries` to read the full entry.
    """
    entries = _load_pinned_entries()
    return {k: v["sha256"] for k, v in entries.items() if "sha256" in v}


def _load_pinned_entries() -> dict[str, dict]:
    """Returns {model_name: {"sha256": str, "size"?: int}}.

    Tolerates the legacy bare-string form; unknown keys inside the
    mapping are preserved on round-trip via the raw YAML but we only
    surface the ones we care about here.
    """
    import yaml

    p = _model_hashes_path()
    if not p.exists():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    out: dict[str, dict] = {}
    if not isinstance(data, dict):
        return out
    for k, v in data.items():
        name = str(k)
        if isinstance(v, str):
            out[name] = {"sha256": v}
        elif isinstance(v, dict) and isinstance(v.get("sha256"), str):
            entry: dict = {"sha256": v["sha256"]}
            if isinstance(v.get("size"), int):
                entry["size"] = v["size"]
            out[name] = entry
    return out


def _save_pinned_hashes(pins: dict[str, str]) -> None:
    """Legacy-compatible save: writes bare strings.

    New callers should use :func:`_save_pinned_entries` to persist size
    alongside the hash.
    """
    entries = {k: {"sha256": v} for k, v in pins.items()}
    # Collapse trivial entries back to bare strings so we don't churn the
    # on-disk format for installs that never pin a size.
    _save_pinned_entries(entries)


def _save_pinned_entries(entries: dict[str, dict]) -> None:
    import yaml

    p = _model_hashes_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    serializable: dict[str, object] = {}
    for name, entry in entries.items():
        if set(entry.keys()) == {"sha256"}:
            serializable[name] = entry["sha256"]
        else:
            serializable[name] = {k: entry[k] for k in sorted(entry)}
    p.write_text(yaml.safe_dump(serializable, sort_keys=True), encoding="utf-8")


def get_pinned_hash(model_name: str) -> str | None:
    """Return the pinned SHA-256 for ``model_name`` or ``None``."""
    return _load_pinned_hashes().get(model_name)


def get_pinned_size(model_name: str) -> int | None:
    """Return the pinned on-disk size (bytes) for ``model_name`` or ``None``.

    Only present for pins recorded after the size-tracking change; older
    pins return ``None`` and callers should treat that as "unknown".
    """
    entry = _load_pinned_entries().get(model_name)
    if entry is None:
        return None
    size = entry.get("size")
    return size if isinstance(size, int) else None


def verify_model(path: Path, model_name: str) -> None:
    """Trust-On-First-Use integrity check.

    - First time we see a given `model_name`: record its SHA256 (and the
      file size, so later UI can warn on partial / truncated copies).
    - Subsequent calls: compare against the pin; raise ValueError on
      mismatch (the user decides whether to trust the new file by
      deleting the pin from model_hashes.yaml).
    """
    actual = sha256_of(path)
    entries = _load_pinned_entries()
    existing = entries.get(model_name)
    if existing is None:
        entries[model_name] = {"sha256": actual, "size": path.stat().st_size}
        _save_pinned_entries(entries)
        return
    expected = existing.get("sha256")
    if actual != expected:
        raise ValueError(
            f"model {model_name!r} SHA256 changed:\n"
            f"  expected (pinned): {expected}\n"
            f"  actual (on disk):  {actual}\n"
            f"If you trust the new file, delete the entry from\n"
            f"  {_model_hashes_path()}\n"
            f"and retry the download."
        )
    # Backfill the size on first match if the pin predates size-tracking.
    if "size" not in existing:
        existing["size"] = path.stat().st_size
        entries[model_name] = existing
        _save_pinned_entries(entries)


# --------------------------------------------------------------------------- #
# Size caps
# --------------------------------------------------------------------------- #

# Be generous — podcasts can be 300 MB+, but cap the worst case.
MAX_MP3_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_FEED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_HTML_BYTES = 10 * 1024 * 1024  # 10 MB


class DownloadTooLargeError(ValueError):
    pass
