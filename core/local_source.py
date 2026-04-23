"""Universal-ingest helpers: local files, folders, and arbitrary URLs.

Three entry points (drop zone, watch folder, folder import) funnel into
the existing ``shows → episodes`` model via synthetic shows. See
``docs/plans/2026-04-23-universal-ingest-design.md``.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from core.state import StateStore

logger = logging.getLogger(__name__)

# Extracted to a module attribute so tests can monkey-patch it and prove
# the mtime+size cache really short-circuits rehashing.
_hashlib_sha256 = hashlib.sha256

# Bytes per read chunk when hashing large files. 1 MiB matches macOS
# APFS's block-read sweet-spot and keeps peak RSS flat.
_HASH_CHUNK = 1024 * 1024


def sha256_of(path: Path, *, state: StateStore) -> str:
    """Return the hex SHA-256 of ``path``, using a (abs_path, size, mtime)
    cache stored in ``state.meta["filehash:<abs_path>"]``.

    Cache format: ``"<size>:<mtime_ns>:<hex>"``. Anything else (missing,
    malformed, size/mtime mismatch) triggers a real hash.
    """
    p = Path(path).resolve()
    st = p.stat()
    meta_key = f"filehash:{p}"

    cached = state.get_meta(meta_key)
    if cached:
        try:
            size_s, mtime_s, hex_s = cached.split(":", 2)
            if int(size_s) == st.st_size and int(mtime_s) == st.st_mtime_ns:
                return hex_s
        except (ValueError, IndexError):
            pass  # malformed — rehash

    h = _hashlib_sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(_HASH_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    hex_s = h.hexdigest()
    state.set_meta(meta_key, f"{st.st_size}:{st.st_mtime_ns}:{hex_s}")
    return hex_s
