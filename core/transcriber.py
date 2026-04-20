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
# Generous timeout: a 60-min podcast at ~1.5× realtime finishes in <6 min
# on an M2 Pro. 10 min covers 2-hour episodes; anything beyond means
# whisper-cli hung on corrupt audio and we want to fail fast.
WHISPER_TIMEOUT_SEC = 600

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
                       model_path: Path = MODEL_PATH,
                       fast_mode: bool = False,
                       processors: int = 1) -> TranscribeResult:
    """Run whisper-cli once and produce <output_dir>/<slug>.md and .srt.

    `fast_mode` toggles the 2-3× speedup decoder flags (beam=1, best-of=1,
    -ac 0, --no-fallback) at slight quality cost. `processors` enables
    whisper-cli's `-p N` audio-split parallelism for long episodes.
    """
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
        if fast_mode:
            cmd += ["-bs", "1", "-bo", "1", "-ac", "0", "--no-fallback"]
        if processors > 1:
            cmd += ["-p", str(processors)]
        if whisper_prompt:
            cmd += ["--prompt", whisper_prompt]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=WHISPER_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired as te:
            # whisper-cli occasionally hangs on corrupt audio. Don't let it
            # block the whole queue for hours. subprocess.run will have
            # killed the child already.
            raise TranscriptionError(
                f"whisper-cli timed out after {WHISPER_TIMEOUT_SEC}s  "
                f"mp3={mp3_path.name}  slug={slug!r}\n"
                f"  partial stderr: {(te.stderr or b'')[-300:]!r}") from te
        if result.returncode != 0:
            raise TranscriptionError(
                f"whisper-cli exit {result.returncode}  "
                f"mp3={mp3_path.name}  model={model_path.name}  "
                f"slug={slug!r}\n"
                f"  stderr (last 400): {(result.stderr or '')[-400:]!r}\n"
                f"  stdout (last 200): {(result.stdout or '')[-200:]!r}")

        # whisper-cli APPENDS '.txt'/'.srt' to the -of prefix — it does NOT
        # replace a suffix. Path.with_suffix() would truncate at the last
        # dot in the slug (e.g. 'Nachhaltigkeit & Co. müssen' → 'Co.txt'),
        # so we'd read the wrong filename. Construct paths by string append.
        txt_path = stem.parent / (stem.name + ".txt")
        srt_src = stem.parent / (stem.name + ".srt")
        if not txt_path.exists() or not srt_src.exists():
            # Give future debugging a head start: list everything whisper
            # DID write so the user (or another agent) can diff expected
            # vs actual path immediately.
            actually_written = sorted(
                p.name for p in stem.parent.iterdir()) if stem.parent.exists() else []
            raise TranscriptionError(
                f"whisper-cli exited 0 but expected outputs missing.\n"
                f"  expected:\n"
                f"    {txt_path}\n"
                f"    {srt_src}\n"
                f"  temp dir contents: {actually_written}\n"
                f"  stdout (last 300): {(result.stdout or '')[-300:]!r}\n"
                f"  stderr (last 300): {(result.stderr or '')[-300:]!r}\n"
                f"  mp3={mp3_path.name}  slug={slug!r}")

        text = txt_path.read_text(encoding="utf-8").strip()
        words = len(text.split())
        if words < MIN_WPM_GUARD:
            raise TranscriptionError(
                f"suspected whisper hallucination / silence: only {words} "
                f"words in transcript (guard threshold = {MIN_WPM_GUARD}).\n"
                f"  mp3={mp3_path.name}  slug={slug!r}\n"
                f"  first 200 chars: {text[:200]!r}")

        md_path = output_dir / f"{slug}.md"
        srt_dest = output_dir / f"{slug}.srt"
        md_path.write_text(
            _fmt_frontmatter(metadata) + _banner(metadata.get("pub_date", "")) + text + "\n",
            encoding="utf-8",
        )
        srt_dest.write_bytes(srt_src.read_bytes())
        return TranscribeResult(md_path=md_path, srt_path=srt_dest, word_count=words)
