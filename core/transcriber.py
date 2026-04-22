"""whisper.cpp wrapper — transcribes a single episode into Obsidian-ready .md + .srt."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping


def _locate_whisper_bin() -> str:
    """Find whisper-cli via PATH, falling back to common Homebrew prefixes.

    Apple Silicon Homebrew: /opt/homebrew/bin
    Intel Homebrew        : /usr/local/bin
    Returns the Apple-Silicon path as a last resort so a missing binary
    surfaces through the existing WHISPER_BIN exists-check rather than
    an unhelpful None.
    """
    found = shutil.which("whisper-cli")
    if found:
        return found
    for p in ("/opt/homebrew/bin/whisper-cli", "/usr/local/bin/whisper-cli"):
        if Path(p).exists():
            return p
    return "/opt/homebrew/bin/whisper-cli"


WHISPER_BIN = _locate_whisper_bin()
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


def _model_name_from_path(model_path: Path) -> str:
    """Reverse ``ggml-<name>.bin`` → ``<name>``.

    Kept tolerant: if the caller passed a weirdly-named model file we just
    return the stem so the fingerprint helper has *something* to key on.
    """
    stem = model_path.stem  # drops .bin
    return stem[5:] if stem.startswith("ggml-") else stem


class TranscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscribeResult:
    md_path: Path
    srt_path: Path
    word_count: int


def _fmt_frontmatter(meta: Mapping[str, str], engine: Mapping[str, str] | None = None) -> str:
    lines = ["---"]
    for key in ("guid", "show_slug", "title", "pub_date", "mp3_url"):
        v = meta.get(key, "")
        lines.append(f'{key}: "{v}"')
    lines.append(f'transcribed_at: "{datetime.now(timezone.utc).isoformat()}"')
    # Engine fingerprint — lets the UI detect whisper/model upgrades and
    # offer a bulk re-transcribe. Missing fields are skipped so we never
    # write a `null`-valued line.
    if engine:
        for key in ("whisper_version", "whisper_model", "model_sha256"):
            v = engine.get(key)
            if v:
                lines.append(f'{key}: "{v}"')
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
        banner += (
            f"> [!warning] ⚠ Stale: Folge ist älter als "
            f"{STALE_YEARS} Jahr(e) — zeitkritische Aussagen prüfen.\n"
        )
    return banner + "\n"


_WHISPER_TS = __import__("re").compile(r"\[\s*(\d+):(\d+):(\d+)\.\d+\s*-->\s*\d+:\d+:\d+\.\d+\s*\]")


def transcribe_episode(
    *,
    mp3_path: Path,
    output_dir: Path,
    slug: str,
    metadata: Mapping[str, str],
    whisper_prompt: str = "",
    language: str = LANGUAGE,
    whisper_bin: str = WHISPER_BIN,
    model_path: Path = MODEL_PATH,
    fast_mode: bool = False,
    processors: int = 1,
    save_srt: bool = True,
    progress_cb=None,
) -> TranscribeResult:
    """Run whisper-cli once and produce <output_dir>/<slug>.md and .srt.

    `fast_mode` toggles the 2-3× speedup decoder flags (beam=1, best-of=1,
    -ac 0, --no-fallback) at slight quality cost. `processors` enables
    whisper-cli's `-p N` audio-split parallelism for long episodes.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Capture engine fingerprint BEFORE spawning whisper — (1) so tests that
    # mock subprocess.run to inspect the transcribe argv see the real
    # transcribe call as the LAST captured invocation, not the version
    # probe, and (2) because the version probe is cached per-process so
    # we pay the cost at most once anyway.
    try:
        from core.engine_version import current_fingerprint

        engine = current_fingerprint(_model_name_from_path(model_path), whisper_bin=whisper_bin)
    except Exception:
        engine = {}

    with tempfile.TemporaryDirectory() as td:
        stem = Path(td) / slug
        cmd = [
            whisper_bin,
            "-m",
            str(model_path),
            "-f",
            str(mp3_path),
            "-l",
            language,
            "-t",
            THREADS,
            "-of",
            str(stem),
            "-otxt",
            "-osrt",
        ]
        if fast_mode:
            cmd += ["-bs", "1", "-bo", "1", "-ac", "0", "--no-fallback"]
        if processors > 1:
            cmd += ["-p", str(processors)]
        if whisper_prompt:
            cmd += ["--prompt", whisper_prompt]
        if progress_cb is None:
            # Classic blocking path — keeps `subprocess.run` so existing
            # tests that mock it stay valid. Used by the CLI, tests,
            # and any caller that doesn't want streaming overhead.
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=WHISPER_TIMEOUT_SEC,
                )
            except subprocess.TimeoutExpired as te:
                raise TranscriptionError(
                    f"whisper-cli timed out after {WHISPER_TIMEOUT_SEC}s  "
                    f"mp3={mp3_path.name}  slug={slug!r}\n"
                    f"  partial stderr: {(te.stderr or b'')[-300:]!r}"
                ) from te
        else:
            # Streaming path — redirects whisper's stdout (where the
            # `[HH:MM:SS.xxx --> ...]` segment lines land) to a temp
            # file, polls that file once per second from a daemon
            # thread, and invokes progress_cb with the last parsed
            # end-timestamp. Still uses subprocess.run so test mocks
            # that patch it continue to work — the mock receives the
            # open file handle via the `stdout=` kwarg and can write
            # simulated segment lines to it.
            import threading

            stdout_log = stem.parent / f"{slug}.stdout.log"
            stop_event = threading.Event()
            poller_state = {"last_size": 0, "max_sec": 0}

            def _drain_once() -> None:
                """Read anything new from stdout_log, fire progress_cb for the
                last timestamp. Safe to call from either thread."""
                try:
                    with open(stdout_log, encoding="utf-8", errors="replace") as f:
                        f.seek(poller_state["last_size"])
                        chunk = f.read()
                        poller_state["last_size"] = f.tell()
                except (FileNotFoundError, OSError):
                    return
                best = poller_state["max_sec"]
                for m in _WHISPER_TS.finditer(chunk):
                    h, mi, s = (int(x) for x in m.groups())
                    sec = h * 3600 + mi * 60 + s
                    if sec > best:
                        best = sec
                if best > poller_state["max_sec"]:
                    poller_state["max_sec"] = best
                    try:
                        progress_cb(best)
                    except Exception:
                        pass

            def _poller() -> None:
                while not stop_event.wait(1.0):
                    _drain_once()

            thread = threading.Thread(target=_poller, name="whisper-poll", daemon=True)
            thread.start()
            try:
                with open(stdout_log, "w", encoding="utf-8") as stdout_f:
                    try:
                        result = subprocess.run(
                            cmd,
                            stdout=stdout_f,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=WHISPER_TIMEOUT_SEC,
                        )
                    except subprocess.TimeoutExpired as te:
                        raise TranscriptionError(
                            f"whisper-cli timed out after {WHISPER_TIMEOUT_SEC}s  "
                            f"mp3={mp3_path.name}  slug={slug!r}\n"
                            f"  partial stderr: {(te.stderr or b'')[-300:]!r}"
                        ) from te
            finally:
                stop_event.set()
                thread.join(timeout=2.0)
            # Final sync drain — catches anything written since the last
            # 1-s tick, and also catches fully-mocked (instant) runs
            # that never gave the poller a chance to tick.
            _drain_once()
            # Surface whisper's stdout via `result.stdout` so the error
            # paths below that inspect it still have useful context.
            try:
                result.stdout = stdout_log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        if result.returncode != 0:
            raise TranscriptionError(
                f"whisper-cli exit {result.returncode}  "
                f"mp3={mp3_path.name}  model={model_path.name}  "
                f"slug={slug!r}\n"
                f"  stderr (last 400): {(result.stderr or '')[-400:]!r}\n"
                f"  stdout (last 200): {(result.stdout or '')[-200:]!r}"
            )

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
            actually_written = (
                sorted(p.name for p in stem.parent.iterdir()) if stem.parent.exists() else []
            )
            raise TranscriptionError(
                f"whisper-cli exited 0 but expected outputs missing.\n"
                f"  expected:\n"
                f"    {txt_path}\n"
                f"    {srt_src}\n"
                f"  temp dir contents: {actually_written}\n"
                f"  stdout (last 300): {(result.stdout or '')[-300:]!r}\n"
                f"  stderr (last 300): {(result.stderr or '')[-300:]!r}\n"
                f"  mp3={mp3_path.name}  slug={slug!r}"
            )

        text = txt_path.read_text(encoding="utf-8").strip()
        words = len(text.split())
        if words < MIN_WPM_GUARD:
            raise TranscriptionError(
                f"suspected whisper hallucination / silence: only {words} "
                f"words in transcript (guard threshold = {MIN_WPM_GUARD}).\n"
                f"  mp3={mp3_path.name}  slug={slug!r}\n"
                f"  first 200 chars: {text[:200]!r}"
            )

        md_path = output_dir / f"{slug}.md"
        srt_dest = output_dir / f"{slug}.srt"
        md_path.write_text(
            _fmt_frontmatter(metadata, engine)
            + _banner(metadata.get("pub_date", ""))
            + text
            + "\n",
            encoding="utf-8",
        )
        # SRT is opt-in. Markdown is always saved; SRT carries per-segment
        # timestamps and is only useful if the user wants to quote passages
        # with an "at 12:34" reference. When disabled we leave srt_dest
        # un-written — downstream consumers (e.g. core.stats._duration_from_srt)
        # already handle a non-existent SRT path gracefully.
        if save_srt:
            srt_dest.write_bytes(srt_src.read_bytes())
        return TranscribeResult(md_path=md_path, srt_path=srt_dest, word_count=words)
