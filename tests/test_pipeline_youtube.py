"""Pipeline integration for YouTube-source shows.

A YouTube episode dispatches to a captions-first / whisper-fallback path
inside core.pipeline. The episode dict's `mp3_url` carries the YouTube
watch URL (set by the YouTube discovery layer); the `PipelineContext`
gains optional source/preference/channel-id fields populated by the
worker_thread per-show.
"""

from pathlib import Path
from unittest.mock import patch

from core.library import LibraryIndex
from core.pipeline import PipelineContext, process_episode
from core.state import StateStore


def _yt_ctx(tmp_path: Path, *, pref: str = "captions") -> PipelineContext:
    state = StateStore(tmp_path / "s.sqlite")
    state.init_schema()
    out = tmp_path / "out"
    out.mkdir()
    lib = LibraryIndex(out)
    return PipelineContext(
        state=state,
        library=lib,
        output_root=out,
        whisper_prompt="",
        retention_days=7,
        delete_mp3_after=True,
        source="youtube",
        youtube_transcript_pref=pref,
        youtube_channel_id="UCabcdefghijklmnopqrstuv",
    )


def _seed_yt_episode(ctx: PipelineContext, *, guid: str = "yt1") -> None:
    ctx.state.upsert_episode(
        show_slug="ch",
        guid=guid,
        title="My Video",
        pub_date="2026-04-15",
        mp3_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )


_FAKE_SRT = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"


def test_youtube_episode_uses_captions_when_available(tmp_path: Path):
    ctx = _yt_ctx(tmp_path, pref="captions")
    _seed_yt_episode(ctx)

    called = {"captions": False, "audio": False, "whisper": False}

    def fake_captions(video_id, basename, *, lang="en", auto_ok=False):
        called["captions"] = True
        srt = basename.with_suffix(".srt")
        srt.parent.mkdir(parents=True, exist_ok=True)
        srt.write_text(_FAKE_SRT, encoding="utf-8")
        return srt

    def fake_audio(*a, **kw):
        called["audio"] = True

    def fake_whisper(*a, **kw):
        called["whisper"] = True

    with (
        patch("core.youtube_captions.fetch_manual_captions", side_effect=fake_captions),
        patch("core.youtube_audio.download_audio", side_effect=fake_audio),
        patch("core.pipeline.transcribe_episode", side_effect=fake_whisper),
    ):
        r = process_episode("yt1", ctx)

    assert called["captions"] is True
    assert called["whisper"] is False
    assert called["audio"] is False
    assert r.action == "transcribed"
    assert ctx.state.get_episode("yt1")["status"] == "done"

    show_dir = ctx.output_root / "ch"
    mds = list(show_dir.glob("*.md"))
    srts = list(show_dir.glob("*.srt"))
    assert len(mds) == 1
    assert len(srts) == 1
    body = mds[0].read_text(encoding="utf-8")
    assert "source: youtube" in body
    assert "youtube_id: dQw4w9WgXcQ" in body
    assert "channel_id: UCabcdefghijklmnopqrstuv" in body
    assert "transcript_source: captions" in body


def test_youtube_episode_falls_back_to_whisper_when_no_captions(tmp_path: Path):
    from core.youtube_captions import NoCaptionsAvailable

    ctx = _yt_ctx(tmp_path, pref="captions")
    _seed_yt_episode(ctx, guid="yt2")

    called = {"captions": False, "audio": False, "whisper": False}

    def fake_captions(*a, **kw):
        called["captions"] = True
        raise NoCaptionsAvailable("none")

    def fake_audio(video_id, target_mp3, **kw):
        called["audio"] = True
        target_mp3.parent.mkdir(parents=True, exist_ok=True)
        target_mp3.write_bytes(b"\x00" * 1024)
        return target_mp3

    class _R:
        md_path: Path
        srt_path: Path
        word_count: int = 5

        def __init__(self, md, srt):
            self.md_path = md
            self.srt_path = srt

    def fake_whisper(*, mp3_path, output_dir, slug, **kw):
        called["whisper"] = True
        output_dir.mkdir(parents=True, exist_ok=True)
        srt = output_dir / f"{slug}.srt"
        srt.write_text(_FAKE_SRT, encoding="utf-8")
        md = output_dir / f"{slug}.md"
        md.write_text('---\nguid: "yt2"\n---\n', encoding="utf-8")
        return _R(md, srt)

    with (
        patch("core.youtube_captions.fetch_manual_captions", side_effect=fake_captions),
        patch("core.youtube_audio.download_audio", side_effect=fake_audio),
        patch("core.pipeline.transcribe_episode", side_effect=fake_whisper),
    ):
        r = process_episode("yt2", ctx)

    assert called["captions"] is True
    assert called["audio"] is True
    assert called["whisper"] is True
    assert r.action == "transcribed"
    assert ctx.state.get_episode("yt2")["status"] == "done"


def test_youtube_episode_whisper_pref_skips_captions(tmp_path: Path):
    ctx = _yt_ctx(tmp_path, pref="whisper")
    _seed_yt_episode(ctx, guid="yt3")

    called = {"captions": False, "audio": False, "whisper": False}

    def fake_captions(*a, **kw):
        called["captions"] = True

    def fake_audio(video_id, target_mp3, **kw):
        called["audio"] = True
        target_mp3.parent.mkdir(parents=True, exist_ok=True)
        target_mp3.write_bytes(b"\x00" * 1024)
        return target_mp3

    class _R:
        word_count = 5

        def __init__(self, md, srt):
            self.md_path = md
            self.srt_path = srt

    def fake_whisper(*, mp3_path, output_dir, slug, **kw):
        called["whisper"] = True
        output_dir.mkdir(parents=True, exist_ok=True)
        srt = output_dir / f"{slug}.srt"
        srt.write_text(_FAKE_SRT, encoding="utf-8")
        md = output_dir / f"{slug}.md"
        md.write_text('---\nguid: "yt3"\n---\n', encoding="utf-8")
        return _R(md, srt)

    with (
        patch("core.youtube_captions.fetch_manual_captions", side_effect=fake_captions),
        patch("core.youtube_audio.download_audio", side_effect=fake_audio),
        patch("core.pipeline.transcribe_episode", side_effect=fake_whisper),
    ):
        r = process_episode("yt3", ctx)

    assert called["captions"] is False
    assert called["audio"] is True
    assert called["whisper"] is True
    assert r.action == "transcribed"
