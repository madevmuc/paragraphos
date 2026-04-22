"""SRT on/off gate in transcribe_episode.

Markdown is always written; the SRT copy to the output directory is
skipped when ``save_srt=False``. We exercise the same fake-whisper
fixture used by test_transcriber.py — whisper-cli itself still writes
the SRT into the temp dir (via the ``-osrt`` flag); the gate lives on
the copy-to-output step.
"""

from pathlib import Path
from unittest.mock import patch

from core.transcriber import transcribe_episode


def _append_ext(prefix: Path, ext: str) -> Path:
    return prefix.parent / (prefix.name + ext)


def _fake_whisper_ok(cmd, *a, **kw):
    prefix = None
    for i, arg in enumerate(cmd):
        if arg == "-of":
            prefix = Path(cmd[i + 1])
            break
    assert prefix is not None
    _append_ext(prefix, ".txt").write_text("word " * 500, encoding="utf-8")
    _append_ext(prefix, ".srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\ntext\n", encoding="utf-8"
    )

    class R:
        returncode = 0
        stdout = ""
        stderr = ""

    return R()


_META = {
    "guid": "g",
    "title": "Sample",
    "show_slug": "demo",
    "pub_date": "2026-04-01",
    "mp3_url": "http://x/ep.mp3",
}


def test_transcribe_writes_srt_when_save_srt_true(tmp_path: Path):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"fake")
    out_dir = tmp_path / "out" / "demo"
    with patch("core.transcriber.subprocess.run", side_effect=_fake_whisper_ok):
        r = transcribe_episode(
            mp3_path=mp3,
            output_dir=out_dir,
            slug="2026-04-01_1_sample",
            metadata=_META,
            save_srt=True,
        )
    assert r.md_path.exists()
    assert r.srt_path.exists()
    assert list(out_dir.glob("*.srt")) == [r.srt_path]


def test_transcribe_skips_srt_when_save_srt_false(tmp_path: Path):
    mp3 = tmp_path / "ep.mp3"
    mp3.write_bytes(b"fake")
    out_dir = tmp_path / "out" / "demo"
    with patch("core.transcriber.subprocess.run", side_effect=_fake_whisper_ok):
        r = transcribe_episode(
            mp3_path=mp3,
            output_dir=out_dir,
            slug="2026-04-01_1_sample",
            metadata=_META,
            save_srt=False,
        )
    assert r.md_path.exists()
    # No .srt should have been copied into the user's output directory.
    assert list(out_dir.glob("*.srt")) == []
    assert not r.srt_path.exists()
