from pathlib import Path
from unittest.mock import patch

import pytest

from core.transcriber import TranscriptionError, transcribe_episode


def _fake_whisper_ok(cmd, *a, **kw):
    """Simulate whisper-cli success: write .txt + .srt at -of prefix."""
    prefix = None
    for i, arg in enumerate(cmd):
        if arg in ("-of", "--output-file"):
            prefix = Path(cmd[i + 1]); break
    assert prefix is not None
    prefix.with_suffix(".txt").write_text(
        "word " * 500, encoding="utf-8")
    prefix.with_suffix(".srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\ntext\n", encoding="utf-8")

    class R:
        returncode = 0; stdout = ""; stderr = ""
    return R()


def _fake_whisper_halluc(cmd, *a, **kw):
    prefix = None
    for i, arg in enumerate(cmd):
        if arg == "-of": prefix = Path(cmd[i + 1]); break
    prefix.with_suffix(".txt").write_text("a b c d", encoding="utf-8")
    prefix.with_suffix(".srt").write_text("1\n", encoding="utf-8")

    class R: returncode = 0; stdout = ""; stderr = ""
    return R()


def test_transcribe_writes_md_and_srt(tmp_path: Path):
    mp3 = tmp_path / "ep.mp3"; mp3.write_bytes(b"fake")
    out_dir = tmp_path / "out" / "demo"
    with patch("core.transcriber.subprocess.run", side_effect=_fake_whisper_ok):
        r = transcribe_episode(
            mp3_path=mp3, output_dir=out_dir, slug="2026-04-01_1_sample",
            metadata={"guid": "g", "title": "Sample", "show_slug": "demo",
                      "pub_date": "2026-04-01", "mp3_url": "http://x/ep.mp3"},
            whisper_prompt="Test prompt",
        )
    assert r.md_path.exists()
    assert r.srt_path.exists()
    text = r.md_path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'guid: "g"' in text
    assert 'show_slug: "demo"' in text
    assert "word word word" in text


def test_transcribe_hallucination_raises(tmp_path: Path):
    mp3 = tmp_path / "ep.mp3"; mp3.write_bytes(b"x")
    with patch("core.transcriber.subprocess.run", side_effect=_fake_whisper_halluc):
        with pytest.raises(TranscriptionError, match="hallucination"):
            transcribe_episode(
                mp3_path=mp3, output_dir=tmp_path / "out", slug="2026-01-01_1_s",
                metadata={"guid": "g", "title": "T", "show_slug": "d",
                          "pub_date": "2026-01-01", "mp3_url": "u"},
            )


def test_transcribe_stale_banner(tmp_path: Path):
    mp3 = tmp_path / "ep.mp3"; mp3.write_bytes(b"x")
    with patch("core.transcriber.subprocess.run", side_effect=_fake_whisper_ok):
        r = transcribe_episode(
            mp3_path=mp3, output_dir=tmp_path / "out", slug="2020-01-01_0_old",
            metadata={"guid": "g", "title": "Old", "show_slug": "d",
                      "pub_date": "2020-01-01", "mp3_url": "u"},
        )
    md = r.md_path.read_text(encoding="utf-8")
    assert "Stale" in md or "stale" in md.lower()


def test_transcribe_nonzero_exit_raises(tmp_path: Path):
    mp3 = tmp_path / "ep.mp3"; mp3.write_bytes(b"x")
    def fake(cmd, *a, **kw):
        class R: returncode = 1; stdout = ""; stderr = "model not found"
        return R()
    with patch("core.transcriber.subprocess.run", side_effect=fake):
        with pytest.raises(TranscriptionError, match="exit 1"):
            transcribe_episode(
                mp3_path=mp3, output_dir=tmp_path / "out", slug="s",
                metadata={"guid": "g", "title": "T", "show_slug": "d",
                          "pub_date": "2026-04-01", "mp3_url": "u"},
            )
