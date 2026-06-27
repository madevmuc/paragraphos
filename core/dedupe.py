"""Re-upload near-duplicate detection (roadmap 3.5).

Detect likely re-uploads of the same episode by **title similarity** — feeds and
channels frequently re-post the same content with a tweaked title ("(re-upload)",
punctuation/spelling drift). This is a non-destructive *reporting* helper: it
surfaces candidate duplicate pairs for the user to act on rather than silently
skipping episodes (a false positive would drop a legitimate episode).

Audio-fingerprint dedup (catching re-uploads with unrelated titles) is the
heavier follow-up — see ``docs/plans/dedupe-fingerprint-design.md``.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_NOISE = re.compile(r"[^\w\s]", re.UNICODE)
_WS = re.compile(r"\s+")
# common re-upload markers + trivial connector words that shouldn't drive a match
_DROP_WORDS = {"reupload", "re", "upload", "und", "and", "the", "der", "die", "das", "a", "an"}


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation + re-upload markers, collapse whitespace."""
    t = (title or "").lower()
    t = _NOISE.sub(" ", t)
    words = [w for w in _WS.sub(" ", t).strip().split(" ") if w and w not in _DROP_WORDS]
    return " ".join(words)


def title_similarity(a: str, b: str) -> float:
    """Similarity in [0, 1] between two titles after normalisation."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def find_near_duplicates(
    items: list[tuple[str, str]], *, threshold: float = 0.85
) -> list[tuple[str, str]]:
    """Return ``(guid_a, guid_b)`` pairs whose titles exceed ``threshold``.

    ``items`` is a list of ``(guid, title)``. O(n²); fine for a single show's
    episode list."""
    pairs: list[tuple[str, str]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if title_similarity(items[i][1], items[j][1]) >= threshold:
                pairs.append((items[i][0], items[j][0]))
    return pairs
