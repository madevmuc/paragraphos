"""Bulk export of selected transcripts (roadmap 4.1).

Export a list of transcript items (``{"title", "text"}``) to a single file in
Markdown, JSON, HTML, or PDF. Markdown / JSON / HTML are always available; PDF is
best-effort via ``fpdf2`` (listed in requirements) and raises a clear error if
the optional dependency isn't installed.
"""

from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path

# Confidence markers (``==word==``, 1.3) → <mark> in HTML output.
_HIGHLIGHT_RE = re.compile(r"==(.+?)==", re.DOTALL)

# SRT cue timestamp line: ``00:00:01,000 --> 00:00:03,000`` (start captured).
_SRT_TIME_RE = re.compile(r"(\d\d:\d\d:\d\d)[,.]\d\d\d\s*-->")


def _parse_srt_cues(srt_text: str) -> list[tuple[str, str]]:
    """Parse SRT into ``[(start "HH:MM:SS", text), …]`` (milliseconds dropped).

    Tolerant of stray index lines / CRLF / multi-line cue text; cues without a
    parseable timestamp or with empty text are skipped."""
    cues: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", (srt_text or "").replace("\r\n", "\n").strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        ts = ti = None
        for i, ln in enumerate(lines):
            m = _SRT_TIME_RE.match(ln.strip())
            if m:
                ts, ti = m.group(1), i
                break
        if ts is None:
            continue
        text = " ".join(lines[ti + 1 :]).strip()
        if text:
            cues.append((ts, text))
    return cues


def _mark_html(escaped: str) -> str:
    """Turn ``==word==`` confidence markers in already-escaped text into <mark>."""
    return _HIGHLIGHT_RE.sub(r"<mark>\1</mark>", escaped)


class BulkExportError(RuntimeError):
    pass


def _export_md(items: list[dict], dest: Path) -> None:
    parts = []
    for it in items:
        parts.append(f"# {it.get('title', 'Untitled')}\n\n{it.get('text', '')}\n")
    dest.write_text("\n\n---\n\n".join(parts), encoding="utf-8")


_HTML_STYLE = (
    "body{max-width:42rem;margin:2rem auto;padding:0 1rem;"
    "font:16px/1.6 -apple-system,Helvetica,Arial,sans-serif;color:#1a1a1a;background:#fff}"
    "h1{font-size:1.5rem;margin:2rem 0 .5rem}article+article{border-top:1px solid #ddd}"
    "mark{background:#fff3b0;padding:0 .1em}p{margin:.6rem 0;white-space:pre-wrap}"
    ".cue{margin:.35rem 0;display:flex;gap:.6rem}"
    ".ts{color:#888;font-variant-numeric:tabular-nums;font-size:.85em;"
    "white-space:nowrap;user-select:none;flex:none}"
    "@media(prefers-color-scheme:dark){body{color:#e6e6e6;background:#1a1a1a}"
    "article+article{border-color:#444}mark{background:#5a4a00;color:#fff}}"
)


def _html_body_from_text(text: str) -> str:
    """Plain-text fallback body: escape + mark, split into <p> on blank lines."""
    paras = []
    for para in re.split(r"\n\s*\n", text or ""):
        if not para.strip():
            continue
        paras.append(f"<p>{_mark_html(_html.escape(para))}</p>")
    return "\n".join(paras)


def _html_body_from_srt(srt_text: str) -> str:
    """Timestamped body: one row per SRT cue, ``[HH:MM:SS] text``."""
    rows = []
    for ts, text in _parse_srt_cues(srt_text):
        rows.append(
            f'<div class="cue"><span class="ts">{ts}</span>'
            f"<span>{_mark_html(_html.escape(text))}</span></div>"
        )
    return "\n".join(rows)


def _export_html(items: list[dict], dest: Path) -> None:
    """Render the items as one clean, self-contained HTML document.

    When an item carries SRT (``it["srt"]``) the body shows timestamped cues
    (``[HH:MM:SS] text``); otherwise it falls back to plain paragraphs from
    ``it["text"]``. Confidence markers (``==word==``) render as <mark>."""
    blocks: list[str] = []
    for it in items:
        title = _html.escape(it.get("title", "Untitled"))
        srt = it.get("srt")
        body = _html_body_from_srt(srt) if srt and _parse_srt_cues(srt) else None
        if not body:
            body = _html_body_from_text(it.get("text", "") or "")
        blocks.append(f"<article>\n<h1>{title}</h1>\n{body}\n</article>")
    doc = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Paragraphos transcripts</title>\n"
        f"<style>{_HTML_STYLE}</style>\n</head>\n<body>\n"
        + "\n".join(blocks)
        + "\n</body>\n</html>\n"
    )
    dest.write_text(doc, encoding="utf-8")


def _export_json(items: list[dict], dest: Path) -> None:
    payload = [{"title": it.get("title", ""), "text": it.get("text", "")} for it in items]
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_pdf(items: list[dict], dest: Path) -> None:
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise BulkExportError(
            "PDF export needs the optional 'fpdf2' package — install it "
            "(pip install fpdf2) or export to Markdown/JSON instead."
        ) from e
    try:
        from fpdf.errors import FPDFException
    except ImportError:  # pragma: no cover - very old fpdf2
        FPDFException = Exception

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    try:
        for it in items:
            pdf.add_page()
            # Reset x to the left margin before each block: newer fpdf2 leaves
            # the cursor at the RIGHT margin after multi_cell(0, …), so the next
            # full-width multi_cell would compute ~0 usable width and raise
            # "Not enough horizontal space to render a single character".
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", style="B", size=14)
            pdf.multi_cell(0, 8, it.get("title", "Untitled"))
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", size=11)
            # latin-1 fallback: core fonts can't encode all of Unicode.
            text = (it.get("text", "") or "").encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 6, text)
        pdf.output(str(dest))
    except FPDFException as e:
        # Pathological layout (e.g. an unbreakable token wider than the page) —
        # degrade to a clear error instead of crashing the caller.
        raise BulkExportError(f"PDF export failed to render: {e}") from e


def export(items: list[dict], fmt: str, dest) -> Path:
    """Export ``items`` to ``dest`` in ``md`` | ``json`` | ``html`` | ``pdf``."""
    dest = Path(dest)
    fmt = (fmt or "").lower()
    if fmt in ("md", "markdown"):
        _export_md(items, dest)
    elif fmt == "json":
        _export_json(items, dest)
    elif fmt in ("html", "htm"):
        _export_html(items, dest)
    elif fmt == "pdf":
        _export_pdf(items, dest)
    else:
        raise BulkExportError(f"unsupported export format: {fmt!r} (use md, json, html, or pdf)")
    return dest
