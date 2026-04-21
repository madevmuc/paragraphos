"""Whisper prompt auto-suggestion from RSS metadata."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Mapping

# Capitalized word runs (incl. Umlauts), 3+ letters, allow internal hyphen.
# Optionally a second capitalized word for names like "Tobias Schulte".
_CAP_WORD = re.compile(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]{2,}(?:\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]{2,})?\b")

_STOPWORDS = {
    "Der",
    "Die",
    "Das",
    "Den",
    "Dem",
    "Des",
    "Ein",
    "Eine",
    "Einen",
    "Einer",
    "Eines",
    "Und",
    "Oder",
    "Aber",
    "Mit",
    "Ohne",
    "Für",
    "Von",
    "Zu",
    "Ist",
    "Sind",
    "War",
    "Waren",
    "Wird",
    "Werden",
    "Wie",
    "Was",
    "Wer",
    "Wo",
    "Wann",
    "Warum",
    "Folge",
    "Episode",
    "Podcast",
    "Teil",
    "Heute",
    "Hier",
    "Dann",
    "Dass",
    "Damit",
}


def suggest_whisper_prompt(
    *,
    title: str,
    author: str,
    episodes: Iterable[Mapping[str, str]],
    top_k: int = 15,
    max_chars: int = 450,
) -> str:
    text = " ".join((e.get("title", "") + " " + e.get("description", "")) for e in episodes)
    candidates = [m.group(0).strip() for m in _CAP_WORD.finditer(text)]
    counts = Counter(c for c in candidates if c not in _STOPWORDS)
    top = [w for w, _ in counts.most_common(top_k)]
    parts = [f"{title}."]
    if author:
        parts.append(f"Host/Autor: {author}.")
    if top:
        parts.append("Begriffe: " + ", ".join(top) + ".")
    out = " ".join(parts)
    return out[:max_chars]
