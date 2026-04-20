"""Expose curated whisper_prompts for the built-in real-estate shows.

Precedence (first hit wins):

1. `data/default_prompts.yaml` inside the Paragraphos repo — the snapshot
   that travels with the repo after extraction from knowledge-hub.
2. Legacy `../transcribe.py` in the same source tree — kept for continuity
   while Paragraphos code still lives under knowledge-hub.
3. Empty dict — bundled `.app` installs on any other machine.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

SHOWS_PROMPTS: dict[str, str] = {}

_HERE = Path(__file__).resolve().parent
_YAML = _HERE / "data" / "default_prompts.yaml"
_LEGACY = _HERE.parent / "transcribe.py"

if _YAML.exists():
    try:
        data = yaml.safe_load(_YAML.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            SHOWS_PROMPTS = {str(k): str(v) for k, v in data.items()}
    except yaml.YAMLError:
        SHOWS_PROMPTS = {}
elif _LEGACY.exists():
    try:
        _spec = importlib.util.spec_from_file_location("_legacy_transcribe", _LEGACY)
        _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        sys.modules["_legacy_transcribe"] = _mod
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        SHOWS_PROMPTS = {slug: cfg.get("whisper_prompt", "") for slug, cfg in _mod.SHOWS.items()}
    except Exception:
        SHOWS_PROMPTS = {}
