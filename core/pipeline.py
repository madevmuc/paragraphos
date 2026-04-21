"""End-to-end episode pipeline: dedup → download → transcribe → retention."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from core.downloader import download_mp3
from core.library import LibraryIndex
from core.sanitize import sanitize_filename
from core.state import EpisodeStatus, StateStore
from core.transcriber import TranscriptionError, transcribe_episode

logger = logging.getLogger(__name__)

_DISK_GUARD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


class DiskSpaceError(RuntimeError):
    pass


@dataclass
class PipelineContext:
    state: StateStore
    library: LibraryIndex
    output_root: Path
    whisper_prompt: str
    retention_days: int
    delete_mp3_after: bool
    language: str = "de"
    model_name: str = "large-v3-turbo"
    fast_mode: bool = False
    processors: int = 1


@dataclass(frozen=True)
class PipelineResult:
    action: Literal["transcribed", "skipped", "failed"]
    guid: str
    detail: str = ""


def build_slug(pub_date: str, title: str, episode_number: str = "0000") -> str:
    """YYYY-MM-DD_<ep-num>_<sanitized-title>."""
    pd = pub_date[:10] if pub_date else "1970-01-01"
    title_part = sanitize_filename(title, max_bytes=120)
    ep = episode_number or "0000"
    return f"{pd}_{ep}_{title_part}"


def _guard_disk(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < _DISK_GUARD_BYTES:
        raise DiskSpaceError(f"only {free // 1024**2} MB free at {path}")


@dataclass(frozen=True)
class DownloadOutcome:
    """Result of the download phase.

    If ``result`` is set, the episode is done (dedup skip) or failed before
    transcription could start. Otherwise ``mp3_path`` / ``show_dir`` / ``slug``
    carry the artefacts the transcribe phase needs.
    """

    guid: str
    result: PipelineResult | None = None  # terminal (skipped/failed)
    mp3_path: Path | None = None
    show_dir: Path | None = None
    slug: str | None = None
    ep: dict | None = None


def download_phase(
    guid: str, ctx: PipelineContext, *, episode_number: str = "0000"
) -> DownloadOutcome:
    """Dedup + download. Terminal results are folded into DownloadOutcome.result."""
    ep = ctx.state.get_episode(guid)
    if ep is None:
        raise ValueError(f"unknown guid {guid}")

    slug = build_slug(ep["pub_date"], ep["title"], episode_number)

    # 1) Dedup
    dup = ctx.library.check_dedup(guid=guid, filename_key=slug)
    if dup.matched:
        ctx.state.set_status(guid, EpisodeStatus.DONE)
        return DownloadOutcome(
            guid=guid,
            result=PipelineResult("skipped", guid, f"dedup/{dup.reason} → {dup.path}"),
        )

    # 2) Download
    from core.security import safe_path_within

    show_dir = ctx.output_root / ep["show_slug"]
    audio_dir = show_dir / "audio"
    mp3_path = audio_dir / f"{slug}.mp3"
    safe_path_within(ctx.output_root, mp3_path)
    safe_path_within(ctx.output_root, show_dir / f"{slug}.md")
    try:
        _guard_disk(audio_dir)
        ctx.state.set_status(guid, EpisodeStatus.DOWNLOADING)
        download_mp3(ep["mp3_url"], mp3_path)
    except DiskSpaceError as e:
        ctx.state.set_status(guid, EpisodeStatus.PENDING)
        return DownloadOutcome(
            guid=guid,
            result=PipelineResult("failed", guid, f"disk: {e}"),
        )
    except Exception as e:
        err = (
            f"download failed [{type(e).__name__}]: {e}\n"
            f"  show={ep['show_slug']}  guid={guid}\n"
            f"  url={ep['mp3_url']}\n"
            f"  dest={mp3_path}"
        )
        logger.error("download failed: %s (guid=%s)", ep["show_slug"], guid, exc_info=True)
        ctx.state.set_status(guid, EpisodeStatus.FAILED, error_text=err)
        return DownloadOutcome(
            guid=guid,
            result=PipelineResult("failed", guid, err),
        )
    ctx.state.set_status(guid, EpisodeStatus.DOWNLOADED)
    return DownloadOutcome(
        guid=guid,
        mp3_path=mp3_path,
        show_dir=show_dir,
        slug=slug,
        ep=ep,
    )


def transcribe_phase(outcome: DownloadOutcome, ctx: PipelineContext) -> PipelineResult:
    """Transcribe an already-downloaded episode + run retention."""
    assert outcome.result is None and outcome.ep is not None
    assert outcome.mp3_path is not None and outcome.show_dir is not None
    assert outcome.slug is not None

    guid = outcome.guid
    ep = outcome.ep
    mp3_path = outcome.mp3_path
    show_dir = outcome.show_dir
    slug = outcome.slug

    ctx.state.set_status(guid, EpisodeStatus.TRANSCRIBING)
    from pathlib import Path as _P

    model_path = _P.home() / ".config/open-wispr/models" / f"ggml-{ctx.model_name}.bin"

    # Write % progress into state.meta so the Queue tab can render
    # "transcribing · X%" on the active row. The transcriber uses a
    # subprocess.run + stdout→file + background poller chain that
    # preserves test-mock compatibility.
    audio_sec = int(ep.get("duration_sec") or 0) or 1

    def _write_progress(elapsed_audio_sec: int) -> None:
        pct = max(0, min(99, int(100 * elapsed_audio_sec / audio_sec)))
        try:
            ctx.state.set_meta(f"transcribe_pct:{guid}", str(pct))
        except Exception:
            pass

    try:
        result = transcribe_episode(
            mp3_path=mp3_path,
            output_dir=show_dir,
            slug=slug,
            metadata=ep,
            whisper_prompt=ctx.whisper_prompt,
            language=ctx.language,
            model_path=model_path,
            fast_mode=ctx.fast_mode,
            processors=ctx.processors,
            progress_cb=_write_progress,
        )
    except TranscriptionError as e:
        err = f"transcribe failed: {e}\n  show={ep['show_slug']}  guid={guid}\n  mp3={mp3_path}"
        logger.error("transcribe failed: %s (guid=%s)", ep["show_slug"], guid, exc_info=True)
        ctx.state.set_status(guid, EpisodeStatus.FAILED, error_text=err)
        return PipelineResult("failed", guid, err)
    ctx.library.add(result.md_path)
    from core.stats import _duration_from_srt

    ctx.state.record_completion(guid, result.word_count, _duration_from_srt(result.srt_path))
    ctx.state.set_status(guid, EpisodeStatus.DONE)
    # Clean up stale % so a later re-transcribe of the same guid starts
    # from blank instead of inheriting the previous 99%.
    try:
        ctx.state.set_meta(f"transcribe_pct:{guid}", "")
    except Exception:
        pass

    # Record the engine+model fingerprint of this successful transcribe so
    # Settings can flag drift when whisper-cli or the model is upgraded.
    try:
        import json

        from core.engine_version import current_fingerprint

        ctx.state.set_meta(
            "last_transcribed_version",
            json.dumps(current_fingerprint(ctx.model_name)),
        )
    except Exception:
        # Never let fingerprint bookkeeping break a successful transcribe.
        pass

    # Retention
    if ctx.delete_mp3_after:
        try:
            mp3_path.unlink()
        except OSError:
            pass

    return PipelineResult("transcribed", guid, str(result.md_path))


def process_episode(
    guid: str, ctx: PipelineContext, *, episode_number: str = "0000"
) -> PipelineResult:
    """Serial dedup → download → transcribe → retention (kept for CLI/tests)."""
    outcome = download_phase(guid, ctx, episode_number=episode_number)
    if outcome.result is not None:
        return outcome.result
    return transcribe_phase(outcome, ctx)
