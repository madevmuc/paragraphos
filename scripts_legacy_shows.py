"""Bridge: expose existing per-show whisper_prompts from scripts/transcribe.py.

When Paragraphos runs inside a bundled .app on a different Mac (or anywhere that
doesn't have the knowledge-hub repo at ../transcribe.py), SHOWS_PROMPTS is an
empty dict — the CLI `import-feeds` then just creates shows with empty
prompts, and the user fills them via the Show Details dialog.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_LEGACY = Path(__file__).resolve().parent.parent / "transcribe.py"
SHOWS_PROMPTS: dict[str, str] = {}

if _LEGACY.exists():
    try:
        _spec = importlib.util.spec_from_file_location("_legacy_transcribe", _LEGACY)
        _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        sys.modules["_legacy_transcribe"] = _mod
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        SHOWS_PROMPTS = {
            slug: cfg.get("whisper_prompt", "")
            for slug, cfg in _mod.SHOWS.items()
        }
    except Exception:
        SHOWS_PROMPTS = {}
