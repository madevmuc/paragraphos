"""Engine + model fingerprinting for drift detection.

Transcripts are only as good as the whisper-cli binary and model that
produced them. When either is upgraded, the user may want to bulk
re-transcribe to benefit from the improvement — but that requires
knowing the "last good" fingerprint to compare against. This module
produces stable, cheap fingerprints for both.

Everything here is best-effort: if whisper-cli is missing (first-run
wizard not done) or the pin file is corrupt, we return ``None`` rather
than raising, so callers can gracefully no-op.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache

# Cap at 3s: if whisper-cli is slow to start we don't want to stall the
# UI — the first invocation already paid this cost, so a miss here means
# something is badly wrong and we prefer to return None and move on.
_VERSION_TIMEOUT_SEC = 3


@lru_cache(maxsize=1)
def get_whisper_version(whisper_bin: str | None = None) -> str | None:
    """Return a stable fingerprint for the whisper-cli binary, or None.

    whisper-cli has no ``--version`` flag in the homebrew build — passing
    ``--version`` drops into the help path with the first line being the
    GGML backend banner (e.g. ``load_backend: loaded BLAS backend from
    /opt/homebrew/Cellar/ggml/0.9.11/libexec/…``). That first line embeds
    the GGML version and is stable across invocations of the same build,
    so it doubles as a cheap drift signal: if the user ``brew upgrade``s
    whisper-cpp or ggml, the Cellar path version bumps and we detect it.

    Cached per-process — no need to subprocess for every episode.
    """
    if whisper_bin is None:
        # Import lazily so tests can monkeypatch WHISPER_BIN without
        # triggering module-level filesystem probes.
        from core.transcriber import WHISPER_BIN

        whisper_bin = WHISPER_BIN
    try:
        result = subprocess.run(
            [whisper_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    combined = (result.stdout or "") + (result.stderr or "")
    first = combined.strip().splitlines()[0] if combined.strip() else ""
    return first or None


@lru_cache(maxsize=8)
def get_model_fingerprint(model_name: str) -> str | None:
    """First 12 chars of the TOFU-pinned SHA-256 for ``model_name``, or None.

    Returns None if no pin exists yet (first-run before any successful
    verify) or if the security module blows up on a corrupt pin file.
    """
    try:
        from core.security import get_pinned_hash

        h = get_pinned_hash(model_name)
    except Exception:
        return None
    if not h:
        return None
    return h[:12]


def current_fingerprint(model_name: str, whisper_bin: str | None = None) -> dict[str, str]:
    """Bundle the two fingerprints into a single dict suitable for
    JSON-serialising into ``state.meta`` or transcript frontmatter.

    Missing fields are omitted entirely (rather than serialised as null)
    so downstream consumers can treat presence-of-key as "we knew this
    at transcribe time".
    """
    out: dict[str, str] = {}
    wv = get_whisper_version(whisper_bin)
    if wv:
        out["whisper_version"] = wv
    mf = get_model_fingerprint(model_name)
    if mf:
        out["model_sha256"] = mf
    out["whisper_model"] = model_name
    return out


def reset_cache() -> None:
    """Test hook — clear the per-process cache so tests can simulate
    reinstalls/upgrades without spawning a fresh interpreter."""
    # Tolerate monkeypatched replacements (tests swap in plain lambdas).
    for fn in (get_whisper_version, get_model_fingerprint):
        clear = getattr(fn, "cache_clear", None)
        if callable(clear):
            clear()
