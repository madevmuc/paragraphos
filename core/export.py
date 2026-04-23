"""Export a show's transcripts as a ZIP (no audio).

Also hosts :func:`render_episode_markdown`, the source-aware frontmatter+body
renderer used by the YouTube ingestion path. The legacy podcast path still
builds its frontmatter inline in :mod:`core.transcriber`; this renderer is
the new entry point and keeps podcast output byte-compatible when called
with the default ``source="podcast"``.
"""

from __future__ import annotations

import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# Mirror core.transcriber.STALE_YEARS so both renderers flag the same age.
_STALE_YEARS = 1


def _age_banner(pub_date_str: str) -> str:
    """Return the standard 'Episode vom YYYY-MM-DD (vor N Tagen)' callout
    + a stale warning when the episode is older than _STALE_YEARS. Empty
    string when the date can't be parsed (banner suppressed silently)."""
    try:
        d = date.fromisoformat(pub_date_str[:10])
    except (ValueError, TypeError):
        return ""
    age_days = (date.today() - d).days
    out = f"> [!info] Episode vom {d.isoformat()} (vor {age_days} Tagen)\n"
    if age_days > 365 * _STALE_YEARS:
        out += (
            f"> [!warning] ⚠ Stale: Folge ist älter als "
            f"{_STALE_YEARS} Jahr(e) — zeitkritische Aussagen prüfen.\n"
        )
    return out + "\n"


def export_show(slug: str, output_root: Path, export_dir: Path) -> Path:
    """Create <export_dir>/<slug>-YYYY-MM-DD.zip with all .md + .srt."""
    src = Path(output_root) / slug
    export_dir = Path(export_dir).expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    zip_path = export_dir / f"{slug}-{date_str}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pattern in ("*.md", "*.srt"):
            for f in src.rglob(pattern):
                # Skip anything under audio/
                if "audio" in f.parts:
                    continue
                zf.write(f, arcname=f.relative_to(src))
    return zip_path


def _srt_to_plain_text(srt_text: str) -> str:
    """Strip SRT cue numbers and timestamps, return concatenated dialogue.

    Tolerant of malformed input: anything that isn't an integer-only line or
    a `HH:MM:SS,mmm --> ...` line is treated as caption text.
    """
    out: list[str] = []
    for raw in srt_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        out.append(line)
    return "\n".join(out)


def render_episode_markdown(
    *,
    show_slug: str,
    title: str,
    srt_text: str,
    source: str = "podcast",
    youtube_id: Optional[str] = None,
    channel_id: Optional[str] = None,
    transcript_source: Optional[str] = None,
    pub_date: str = "",
) -> str:
    """Render an episode `.md` (frontmatter + body) for the given source.

    For ``source="youtube"`` the frontmatter gains ``youtube_id``,
    ``youtube_url``, ``channel_id`` and ``transcript_source`` keys, and the
    body is prefixed with a ``[Watch on YouTube](...)`` link. ``pub_date``
    (ISO YYYY-MM-DD) drives the standard age callout that the podcast
    renderer also emits — keeps Obsidian render parity across sources.
    """
    fm: list[str] = ["---"]
    fm.append(f"show_slug: {show_slug}")
    fm.append(f"title: {title}")
    fm.append(f"source: {source}")
    if source == "youtube":
        if youtube_id:
            fm.append(f"youtube_id: {youtube_id}")
            fm.append(f"youtube_url: https://youtu.be/{youtube_id}")
        if channel_id:
            fm.append(f"channel_id: {channel_id}")
        if transcript_source:
            fm.append(f"transcript_source: {transcript_source}")
    fm.append("---")

    body_parts: list[str] = []
    if source == "youtube" and youtube_id:
        body_parts.append(f"[Watch on YouTube](https://youtu.be/{youtube_id})")
        body_parts.append("")
    banner = _age_banner(pub_date)
    if banner:
        body_parts.append(banner.rstrip("\n"))
    body_parts.append(_srt_to_plain_text(srt_text))

    return "\n".join(fm) + "\n\n" + "\n".join(body_parts) + "\n"
