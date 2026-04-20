"""End-to-end pipeline test against real whisper-cli + real MP3.

Opt-in: runs only under `pytest -m integration`. Skipped automatically
if whisper-cli or the MP3 fixture are missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


FIXTURE_MP3 = Path(__file__).parent / "fixtures" / "short.mp3"
WHISPER_BIN = Path("/opt/homebrew/bin/whisper-cli")


def _skip_if_unavailable():
    if not WHISPER_BIN.exists():
        pytest.skip(f"whisper-cli not at {WHISPER_BIN}")
    if not FIXTURE_MP3.exists():
        pytest.skip(f"{FIXTURE_MP3} missing — see README.md in this folder")


def test_transcribe_dotted_slug_real_whisper(tmp_path):
    """Regression: the v0.4.3 'produced no output files' bug, now
    re-checked against the real whisper-cli binary with a dotted slug.
    Proves the fix holds end-to-end, not just in mocks."""
    _skip_if_unavailable()
    from core.transcriber import transcribe_episode
    slug = "2020-05-20_0021_Co. (Kein) Plädoyer für Privatisierung"
    r = transcribe_episode(
        mp3_path=FIXTURE_MP3,
        output_dir=tmp_path / "out",
        slug=slug,
        metadata={"guid": "g", "title": "T", "show_slug": "demo",
                  "pub_date": "2020-05-20", "mp3_url": "http://x"},
        model_path=Path.home() / ".config/open-wispr/models/ggml-base.bin",
    )
    assert r.md_path.exists()
    assert r.srt_path.exists()
    assert r.word_count > 0
