"""whisper.cpp wrapper — transcribes a single episode into Obsidian-ready .md + .srt."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

WHISPER_BIN = "/opt/homebrew/bin/whisper-cli"
MODEL_PATH = Path.home() / ".config" / "open-wispr" / "models" / "ggml-large-v3-turbo.bin"
LANGUAGE = "de"
THREADS = "6"

# Natural German podcast speech runs ~140-180 wpm. Below 30 → silence or hallucination.
MIN_WPM_GUARD = 30

STALE_YEARS = 1


class TranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscribeResult:
    md_path: Path
    srt_path: Path
    word_count: int


def _fmt_frontmatter(meta: Mapping[str, str]) -> str:
    lines = ["---"]
    for key in ("guid", "show_slug", "title", "pub_date", "mp3_url"):
        v = meta.get(key, "")
        lines.append(f'{key}: "{v}"')
    lines.append(f'transcribed_at: "{datetime.now(timezone.utc).isoformat()}"')
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _banner(pub_date_str: str) -> str:
    try:
        d = date.fromisoformat(pub_date_str[:10])
    except (ValueError, TypeError):
        return ""
    age_days = (date.today() - d).days
    banner = f"> [!info] Episode vom {d.isoformat()} (vor {age_days} Tagen)\n"
    if age_days > 365 * STALE_YEARS:
        banner += (f"> [!warning] ⚠ Stale: Folge ist älter als "
                   f"{STALE_YEARS} Jahr(e) — zeitkritische Aussagen prüfen.\n")
    return banner + "\n"


def transcribe_episode(*, mp3_path: Path, output_dir: Path, slug: str,
                       metadata: Mapping[str, str],
                       whisper_prompt: str = "",
                       language: str = LANGUAGE,
                       whisper_bin: str = WHISPER_BIN,
                       model_path: Path = MODEL_PATH) -> TranscribeResult:
    """Run whisper-cli once and produce <output_dir>/<slug>.md and .srt."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        stem = Path(td) / slug
        cmd = [
            whisper_bin,
            "-m", str(model_path),
            "-f", str(mp3_path),
            "-l", language,
            "-t", THREADS,
            "-of", str(stem),
            "-otxt", "-osrt",
        ]
        if whisper_prompt:
            cmd += ["--prompt", whisper_prompt]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise TranscriptionError(
                f"whisper-cli exit {result.returncode}: {result.stderr[:400]}")

        # whisper-cli APPENDS '.txt'/'.srt' to the -of prefix — it does NOT
        # replace a suffix. Path.with_suffix() would truncate at the last
        # dot in the slug (e.g. 'Nachhaltigkeit & Co. müssen' → 'Co.txt'),
        # so we'd read the wrong filename and falsely raise "produced no
        # output files". Construct paths by string append instead.
        txt_path = stem.parent / (stem.name + ".txt")
        srt_src = stem.parent / (stem.name + ".srt")
        if not txt_path.exists() or not srt_src.exists():
            raise TranscriptionError("whisper-cli produced no output files")

        text = txt_path.read_text(encoding="utf-8").strip()
        words = len(text.split())
        if words < MIN_WPM_GUARD:
            raise TranscriptionError(
                f"suspected whisper hallucination: only {words} words")

        md_path = output_dir / f"{slug}.md"
        srt_dest = output_dir / f"{slug}.srt"
        md_path.write_text(
            _fmt_frontmatter(metadata) + _banner(metadata.get("pub_date", "")) + text + "\n",
            encoding="utf-8",
        )
        srt_dest.write_bytes(srt_src.read_bytes())
        return TranscribeResult(md_path=md_path, srt_path=srt_dest, word_count=words)
