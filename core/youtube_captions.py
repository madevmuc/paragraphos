"""YouTube caption fetch (via yt-dlp) and WebVTT → SRT conversion.

Manual (uploader-provided) captions only by default; auto-captions are
opt-in via the `auto_ok` flag.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from core import ytdlp


class NoCaptionsAvailable(RuntimeError):
    """yt-dlp returned no caption file for the requested language/kind."""


_VTT_TS = re.compile(r"(\d{2}:\d{2}:\d{2})\.(\d{3})")


def vtt_to_srt(vtt: str) -> str:
    """Convert WebVTT text to SRT. Drops cue settings + WEBVTT header."""
    lines = vtt.splitlines()
    try:
        i = lines.index("")
        body = lines[i + 1 :]
    except ValueError:
        body = lines

    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in body:
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    out: list[str] = []
    n = 0
    for blk in blocks:
        ts_idx = next((i for i, ln in enumerate(blk) if "-->" in ln), None)
        if ts_idx is None:
            continue
        ts_line = blk[ts_idx]
        ts_line = ts_line.split("  ")[0]
        ts_line = _VTT_TS.sub(r"\1,\2", ts_line)
        text_lines = blk[ts_idx + 1 :]
        if not text_lines:
            continue
        n += 1
        out.append(str(n))
        out.append(ts_line)
        out.extend(text_lines)
        out.append("")
    return "\n".join(out)


def fetch_manual_captions(
    video_id: str,
    out_basename: Path,
    *,
    lang: str = "en",
    auto_ok: bool = False,
) -> Path:
    """Download captions for `video_id`. Returns path to converted .srt.

    `out_basename` is e.g. `/tmp/xyz/video` (no extension); yt-dlp will
    write `<basename>.<lang>.vtt` next to it.
    """
    if not ytdlp.is_installed():
        raise NoCaptionsAvailable("yt-dlp not installed")
    extra = ["--sub-langs", lang, "--skip-download", "--sub-format", "vtt"]
    if auto_ok:
        extra.insert(0, "--write-auto-subs")
    cmd = [
        str(ytdlp.ytdlp_path()),
        "--write-subs",
        *extra,
        "-o",
        str(out_basename),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise NoCaptionsAvailable(proc.stderr.strip())

    vtt_path = out_basename.with_suffix(f".{lang}.vtt")
    if not vtt_path.exists():
        raise NoCaptionsAvailable(f"no caption file produced: {vtt_path}")
    srt_path = out_basename.with_suffix(".srt")
    srt_path.write_text(vtt_to_srt(vtt_path.read_text(encoding="utf-8")), encoding="utf-8")
    return srt_path
