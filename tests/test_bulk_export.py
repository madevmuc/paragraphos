"""Bulk export of selected transcripts (4.1)."""

from __future__ import annotations

import json

import pytest

from core.bulk_export import BulkExportError, export

_ITEMS = [
    {"title": "Episode One", "text": "Hello world.\nSecond line."},
    {"title": "Episode Two", "text": "Another transcript body."},
]


def test_export_markdown(tmp_path):
    dest = tmp_path / "out.md"
    export(_ITEMS, "md", dest)
    body = dest.read_text(encoding="utf-8")
    assert "Episode One" in body
    assert "Episode Two" in body
    assert "Another transcript body." in body


def test_export_json(tmp_path):
    dest = tmp_path / "out.json"
    export(_ITEMS, "json", dest)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert [d["title"] for d in data] == ["Episode One", "Episode Two"]


def test_export_html(tmp_path):
    dest = tmp_path / "out.html"
    export(_ITEMS, "html", dest)
    body = dest.read_text(encoding="utf-8")
    assert body.startswith("<!DOCTYPE html>")
    assert "<title>Paragraphos transcripts</title>" in body
    assert "<h1>Episode One</h1>" in body
    assert "<h1>Episode Two</h1>" in body
    assert "Another transcript body." in body


def test_export_html_escapes_and_marks_confidence(tmp_path):
    items = [{"title": "A & B <tag>", "text": "a ==maybe== word & <b>x</b>"}]
    dest = tmp_path / "out.html"
    export(items, "html", dest)
    body = dest.read_text(encoding="utf-8")
    # HTML-escaped title + body, confidence marker → <mark>
    assert "A &amp; B &lt;tag&gt;" in body
    assert "<mark>maybe</mark>" in body
    assert "&lt;b&gt;x&lt;/b&gt;" in body  # body tags neutralised, not injected


def test_export_html_renders_srt_timestamps(tmp_path):
    srt = (
        "1\n00:00:01,000 --> 00:00:03,000\nHello there\n\n"
        "2\n00:01:05,500 --> 00:01:07,000\nGoodbye ==now==\n"
    )
    items = [{"title": "Ep", "text": "fallback body", "srt": srt}]
    dest = tmp_path / "out.html"
    export(items, "html", dest)
    body = dest.read_text(encoding="utf-8")
    assert '<span class="ts">00:00:01</span>' in body
    assert "Hello there" in body
    assert '<span class="ts">00:01:05</span>' in body
    assert "<mark>now</mark>" in body  # confidence marker survives into cue text
    assert "fallback body" not in body  # SRT present → cues used, not the md text


def test_export_html_falls_back_when_no_srt(tmp_path):
    items = [{"title": "Ep", "text": "just paragraphs", "srt": ""}]
    dest = tmp_path / "out.html"
    export(items, "html", dest)
    body = dest.read_text(encoding="utf-8")
    assert "<p>just paragraphs</p>" in body
    assert 'class="ts"' not in body


def test_export_unknown_format_raises(tmp_path):
    with pytest.raises(BulkExportError):
        export(_ITEMS, "docx", tmp_path / "x.docx")


def test_export_pdf_produces_or_reports(tmp_path):
    dest = tmp_path / "out.pdf"
    try:
        export(_ITEMS, "pdf", dest)
    except BulkExportError as e:
        # Acceptable: PDF dependency not installed — must be a clear message.
        assert "pdf" in str(e).lower()
    else:
        assert dest.exists() and dest.stat().st_size > 0
