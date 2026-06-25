# Load-Management (Hintergrundlast-Stufen) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users choose how hard transcription may drive the Mac via 3 named levels (Leise / Ausgewogen / Volle Leistung), so the machine stays responsive while paragraphos uses otherwise-idle CPU.

**Architecture:** A pure function `core/load.py::resolve_load_profile(level, perf_cores, background_priority)` maps the level to concrete whisper-cli launch parameters — number of parallel worker processes, `-t` thread count, and a macOS scheduling tier (`taskpolicy -b` / `nice` / normal) applied as an **argv prefix** to the whisper-cli command. The level becomes the single source of truth; the old `parallel_transcribe` / `whisper_multiproc` settings are removed (computed now) with a one-time migration. GPU/Metal is untouched.

**Tech Stack:** Python 3, Pydantic v2 settings (`core/models.py`), PyQt6 settings pane, `whisper-cli` (whisper.cpp via Homebrew) launched through `subprocess.run`. macOS-native `nice` + `taskpolicy` (no new deps). pytest, bare-QApplication for any Qt tests.

**Design doc:** `docs/plans/2026-06-25-load-management-design.md`

**Branch / worktree:** main tree on `feat/load-management` (already checked out, clean). The parallel guardrail work lives in its own worktree — do **not** switch branches in this tree.

---

## Task 1: `core/load.py` — pure level→profile resolver

**Files:**
- Create: `core/load.py`
- Test: `tests/test_load_profile.py`

**Step 1: Write the failing tests**

```python
# tests/test_load_profile.py
"""resolve_load_profile maps a user-facing background-load level to concrete
whisper-cli launch parameters. Pure + HW-independent (perf_cores passed in)."""

from __future__ import annotations

from core.load import LoadProfile, describe_profile, resolve_load_profile


def test_quiet_is_minimal_and_background():
    p = resolve_load_profile("quiet", perf_cores=8, background_priority=True)
    assert (p.parallel, p.threads, p.qos) == (1, 2, "background")
    assert p.command_prefix() == ["taskpolicy", "-b"]


def test_balanced_uses_half_the_cores_and_nice():
    p = resolve_load_profile("balanced", perf_cores=8, background_priority=True)
    assert (p.parallel, p.threads, p.qos) == (1, 4, "nice")
    assert p.command_prefix() == ["nice", "-n", "10"]


def test_full_is_polite_when_background_priority_on():
    p = resolve_load_profile("full", perf_cores=8, background_priority=True)
    assert (p.parallel, p.threads, p.qos, p.nice_level) == (2, 4, "nice", 5)
    assert p.command_prefix() == ["nice", "-n", "5"]


def test_full_is_raw_normal_when_background_priority_off():
    p = resolve_load_profile("full", perf_cores=8, background_priority=False)
    assert p.qos == "normal"
    assert p.command_prefix() == []


def test_scales_down_on_a_small_machine():
    p = resolve_load_profile("full", perf_cores=2, background_priority=True)
    assert p.parallel == 1 and p.threads == 2


def test_detection_failure_never_divides_by_zero():
    p = resolve_load_profile("balanced", perf_cores=0, background_priority=True)
    assert p.parallel >= 1 and p.threads >= 1


def test_unknown_level_raises():
    import pytest

    with pytest.raises(ValueError):
        resolve_load_profile("turbo", perf_cores=8, background_priority=True)  # type: ignore[arg-type]


def test_describe_profile_is_human_readable():
    p = resolve_load_profile("balanced", perf_cores=8, background_priority=True)
    text = describe_profile(p)
    assert "1 Episode" in text and "4 Threads" in text
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_load_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.load'`

**Step 3: Write the implementation**

```python
# core/load.py
"""Load-management profiles — map a user-facing background-load level to
concrete whisper-cli launch parameters (parallelism, threads, macOS
scheduling tier).

Pure + dependency-free so it unit-tests without touching hardware. The
caller (ui/worker_thread.py) supplies the detected performance-core count;
core/hw.py does the detection. macOS scheduling tiers are applied as an
argv prefix on the whisper-cli command (thread-safe — no preexec_fn).

Design: docs/plans/2026-06-25-load-management-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LoadLevel = Literal["quiet", "balanced", "full"]
Qos = Literal["background", "nice", "normal"]


@dataclass(frozen=True)
class LoadProfile:
    parallel: int  # concurrent transcribe workers (whisper-cli processes)
    threads: int  # whisper-cli -t
    qos: Qos  # macOS scheduling tier
    nice_level: int  # niceness when qos == "nice" (ignored otherwise)

    def command_prefix(self) -> list[str]:
        """argv prefix that applies the scheduling tier to a launched
        subprocess. Empty list for the normal tier."""
        if self.qos == "background":
            return ["taskpolicy", "-b"]
        if self.qos == "nice":
            return ["nice", "-n", str(self.nice_level)]
        return []


def resolve_load_profile(
    level: LoadLevel,
    *,
    perf_cores: int,
    background_priority: bool,
) -> LoadProfile:
    """Map (level, hardware, polite-flag) → concrete launch parameters.

    ``perf_cores`` is the machine's performance-core count; the caller falls
    back to logical CPUs / a small constant when detection fails. Higher
    levels spend more cores and a less-deferential scheduling tier.
    """
    p = max(1, perf_cores)
    if level == "quiet":
        return LoadProfile(parallel=1, threads=min(2, p), qos="background", nice_level=0)
    if level == "balanced":
        return LoadProfile(parallel=1, threads=max(2, p // 2), qos="nice", nice_level=10)
    if level == "full":
        parallel = 2 if p >= 8 else 1
        threads = max(2, p // parallel)
        if background_priority:
            return LoadProfile(parallel=parallel, threads=threads, qos="nice", nice_level=5)
        return LoadProfile(parallel=parallel, threads=threads, qos="normal", nice_level=0)
    raise ValueError(f"unknown load level: {level!r}")


_TIER_DE = {
    "background": "läuft im Hintergrund (E-Kerne)",
    "nice": "weicht aktiver Nutzung aus",
    "normal": "volle Priorität",
}


def describe_profile(profile: LoadProfile) -> str:
    """Human-readable one-liner for the settings read-out label."""
    episodes = "1 Episode" if profile.parallel == 1 else f"{profile.parallel} Episoden"
    return f"{episodes} × {profile.threads} Threads · {_TIER_DE[profile.qos]}"
```

**Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_load_profile.py -q`
Expected: PASS (8 passed)

**Step 5: Commit**

```bash
git add core/load.py tests/test_load_profile.py
git commit -m "feat(load): pure level→profile resolver (parallelism + threads + qos)"
```

---

## Task 2: `core/models.py` — settings fields + legacy migration

**Files:**
- Modify: `core/models.py` (imports line 7; field lines 84 + 93; `load()` ~169-189; `_apply_hw_defaults` ~199-210)
- Test: `tests/test_load_settings.py`

**Step 1: Write the failing tests**

```python
# tests/test_load_settings.py
"""load_level / background_priority settings: defaults, round-trip, and the
one-time migration off the legacy parallel_transcribe knob."""

from __future__ import annotations

from core.models import Settings


def test_fresh_install_defaults_to_balanced(tmp_path):
    s = Settings.load(tmp_path / "settings.yaml")
    assert s.load_level == "balanced"
    assert s.background_priority is True


def test_round_trips(tmp_path):
    p = tmp_path / "settings.yaml"
    Settings(load_level="quiet", background_priority=False).save(p)
    reloaded = Settings.load(p)
    assert reloaded.load_level == "quiet"
    assert reloaded.background_priority is False


def test_legacy_parallel_2_migrates_to_full(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text("parallel_transcribe: 3\nwhisper_multiproc: 4\n", encoding="utf-8")
    assert Settings.load(p).load_level == "full"


def test_legacy_single_worker_migrates_to_balanced(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text("parallel_transcribe: 1\n", encoding="utf-8")
    assert Settings.load(p).load_level == "balanced"


def test_explicit_load_level_wins_over_legacy(tmp_path):
    p = tmp_path / "settings.yaml"
    p.write_text("load_level: quiet\nparallel_transcribe: 3\n", encoding="utf-8")
    assert Settings.load(p).load_level == "quiet"
```

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_load_settings.py -q`
Expected: FAIL — `load_level` is not a field yet / migration absent.

**Step 3: Edit `core/models.py`**

3a. Imports (line 7) — add `Literal`:
```python
from typing import List, Literal, Optional
```

3b. Remove the legacy field at line 84 (`parallel_transcribe: int = 1`) and replace it in place with the two new fields:
```python
    # Load management — how hard the machine may be driven by transcription.
    # The level derives concrete whisper-cli parallelism + thread count +
    # macOS scheduling tier (see core/load.py); replaces the former
    # parallel_transcribe / whisper_multiproc knobs.
    load_level: Literal["quiet", "balanced", "full"] = "balanced"
    # Run transcription under a deferential scheduling tier so the Mac stays
    # responsive. Implied for quiet/balanced; at "full" this picks nice
    # (polite, default) vs normal (raw maximum) priority.
    background_priority: bool = True
```

3c. Remove the legacy field at line 93 (`whisper_multiproc: int = 1  # whisper-cli -p N ...`). Delete the whole line.

3d. In `load()`, fresh-install branch — drop the `_apply_hw_defaults(s)` call:
```python
        if not path.exists():
            s = cls()
            try:
                s.save(path)
            except Exception:
                pass
            backfill_setup_completed(s)
            return s
```

3e. In `load()`, existing-file branch — run migration before validation:
```python
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _migrate_load_level(data)
        s = cls.model_validate(data)
        backfill_setup_completed(s)
        return s
```

3f. Replace the `_apply_hw_defaults` function (~199-210) with the migration helper:
```python
def _migrate_load_level(data: dict) -> None:
    """Legacy settings.yaml had parallel_transcribe / whisper_multiproc.
    Map an absent load_level onto a level so upgraders keep a sensible
    profile instead of silently dropping to the default. Unknown legacy
    keys are otherwise ignored by Pydantic (extra='ignore')."""
    if "load_level" in data:
        return
    legacy = data.get("parallel_transcribe")
    if isinstance(legacy, int):
        data["load_level"] = "full" if legacy >= 2 else "balanced"
```

**Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_load_settings.py -q`
Expected: PASS (5 passed)

**Step 5: Catch stragglers + commit**

Run: `grep -rn "_apply_hw_defaults\|parallel_transcribe\|whisper_multiproc" --include="*.py" core/ tests/`
Expected: only `core/models.py` migration + the test file should reference the legacy names. If a test references `_apply_hw_defaults`, update/remove it. (Other modules — `worker_thread.py`, `settings_pane.py` — are handled in later tasks; they will still reference the names until then, which is fine.)

```bash
git add core/models.py tests/test_load_settings.py
git commit -m "feat(settings): add load_level/background_priority, migrate off legacy knobs"
```

---

## Task 3: `core/transcriber.py` — threads + launch-prefix params

**Files:**
- Modify: `core/transcriber.py` (`transcribe_episode` signature ~290-304; cmd build ~335-349)
- Test: `tests/test_transcriber_launch.py` (or extend an existing transcriber test — check `tests/` for one that mocks `subprocess.run`)

**Step 1: Write the failing test**

```python
# tests/test_transcriber_launch.py
"""transcribe_episode honours an explicit thread count and a launch prefix
(macOS scheduling tier) on the whisper-cli command line."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from core import transcriber


def _run_capture(**kwargs):
    captured = {}

    def fake_run(cmd, *a, **kw):
        captured["cmd"] = cmd
        # Minimal success stub: whisper writes <stem>.txt; emulate by
        # returning a zero exit. The .txt read is mocked separately below.
        raise transcriber.TranscriptionError("stop after argv capture")

    with mock.patch("core.transcriber.subprocess.run", side_effect=fake_run):
        try:
            transcriber.transcribe_episode(
                mp3_path=Path("/tmp/x.wav"),
                output_dir=Path("/tmp/out"),
                slug="ep",
                metadata={},
                **kwargs,
            )
        except Exception:
            pass
    return captured["cmd"]


def test_threads_flag_uses_explicit_value():
    cmd = _run_capture(threads=4)
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "4"


def test_launch_prefix_prepends_scheduler():
    cmd = _run_capture(threads=2, launch_prefix=["nice", "-n", "10"])
    assert cmd[:3] == ["nice", "-n", "10"]
    # whisper binary comes right after the prefix
    assert cmd[3].endswith("whisper-cli") or "whisper" in cmd[3]


def test_no_prefix_by_default():
    cmd = _run_capture(threads=6)
    assert cmd[0] != "nice" and cmd[0] != "taskpolicy"
```

> Note: adapt the mock to however the repo's existing transcriber tests stub `subprocess.run` + the `<stem>.txt` read (grep `tests/` for `subprocess.run` and `transcribe_episode`). The assertions on `cmd` are the load-bearing part.

**Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_transcriber_launch.py -q`
Expected: FAIL — `transcribe_episode` has no `threads` / `launch_prefix` kwargs.

**Step 3: Edit `core/transcriber.py`**

3a. Add params to the signature (after `processors: int = 1,`):
```python
    processors: int = 1,
    threads: int = int(THREADS),
    launch_prefix: "Sequence[str]" = (),
    save_srt: bool = True,
    progress_cb=None,
```
Ensure `Sequence` is imported (`from typing import Sequence` / `from collections.abc import Sequence` — match the file's existing import style).

3b. Build the cmd with the prefix and the explicit thread count (replace the `-t`, `THREADS` pair and prepend the prefix):
```python
        cmd = [
            *launch_prefix,
            whisper_bin,
            "-m",
            str(model_path),
            "-f",
            str(whisper_input),
            "-l",
            language,
            "-t",
            str(threads),
            "-of",
            str(stem),
            "-otxt",
            "-osrt",
        ]
```

**Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_transcriber_launch.py -q`
Expected: PASS

Also run the existing transcriber tests to confirm no regression (defaults `threads=6`, no prefix → identical argv):
Run: `python -m pytest tests/ -k transcrib -q`
Expected: PASS

**Step 5: Commit**

```bash
git add core/transcriber.py tests/test_transcriber_launch.py
git commit -m "feat(transcriber): accept explicit -t threads + scheduler launch prefix"
```

---

## Task 4: `core/pipeline.py` — thread threads + prefix through PipelineContext

**Files:**
- Modify: `core/pipeline.py` (`PipelineContext` ~line 37; `transcribe_episode` calls ~289-298 and ~534-543)

**Step 1: Add fields to `PipelineContext`** (next to `processors: int = 1`):
```python
    processors: int = 1
    threads: int = 6
    launch_prefix: tuple[str, ...] = ()
```

**Step 2: Pass them at both `transcribe_episode` call sites** — add to each call:
```python
            processors=ctx.processors,
            threads=ctx.threads,
            launch_prefix=ctx.launch_prefix,
```

**Step 3: Verify nothing broke**

Run: `python -m pytest tests/ -k "pipeline or transcrib" -q`
Expected: PASS (defaults keep prior behaviour).

**Step 4: Commit**

```bash
git add core/pipeline.py
git commit -m "feat(pipeline): carry threads + launch_prefix through PipelineContext"
```

---

## Task 5: `ui/worker_thread.py` — resolve profile, drive parallelism + prefix

**Files:**
- Modify: `ui/worker_thread.py` (imports ~40; PipelineContext build ~509-517; `n_tr` ~732)

> Qt worker — not unit-tested headless (repo convention; see the pausing-state design doc). Verified by the manual smoke in Task 8.

**Step 1: Import the resolver** near the other `core` imports:
```python
from core.hw import detect
from core.load import resolve_load_profile
```

**Step 2: Resolve the profile once where `self.settings` is set** (in `__init__`, near line 489 `self.settings = settings`):
```python
        self.settings = settings
        import os

        _mem, _perf = detect()
        self._load_profile = resolve_load_profile(
            self.settings.load_level,
            perf_cores=_perf or (os.cpu_count() or 4),
            background_priority=self.settings.background_priority,
        )
```

**Step 3: Use the profile in the PipelineContext build** (~509-517). Replace `processors=self.settings.whisper_multiproc,` with:
```python
            processors=1,  # whisper_multiproc retired; level controls load
            threads=self._load_profile.threads,
            launch_prefix=tuple(self._load_profile.command_prefix()),
```

**Step 4: Use the profile for the worker count** (~732). Replace:
```python
        n_tr = max(int(self.settings.parallel_transcribe or 1), 1)
```
with:
```python
        n_tr = max(self._load_profile.parallel, 1)
```

**Step 5: Verify imports + suite**

Run: `python -c "import ui.worker_thread"` → Expected: no error.
Run: `python -m pytest tests/ -k worker -q` → Expected: PASS (or unchanged).

**Step 6: Commit**

```bash
git add ui/worker_thread.py
git commit -m "feat(worker): drive transcription parallelism + qos from load profile"
```

---

## Task 6: `ui/settings_pane.py` — replace spinboxes with the Hintergrundlast group

**Files:**
- Modify: `ui/settings_pane.py` (parallel widget 538-550; multiproc widget 569-583; `_do_save` 1052 + 1059; dead helpers ~1148-1180)

> Qt surface — verified by manual smoke (Task 8), not unit tests.

**Step 1: Replace the parallel block (lines 538-550) with the level group.** Remove `rec_n = self._hw_recommendation_value()` too:
```python
        # Hintergrundlast — named levels; each derives whisper parallelism +
        # threads + macOS scheduling tier (core/load.py). Replaces the old
        # Parallel-workers / Multi-processor-split spinboxes.
        from core.load import describe_profile, resolve_load_profile

        self.load_quiet = QRadioButton("Leise — nimmt nur wenig, bleibt unsichtbar")
        self.load_balanced = QRadioButton(
            "Ausgewogen — nutzt freie Kerne, weicht beim Arbeiten zurück"
        )
        self.load_full = QRadioButton("Volle Leistung — so schnell wie möglich")
        self._load_buttons = {
            "quiet": self.load_quiet,
            "balanced": self.load_balanced,
            "full": self.load_full,
        }
        self._load_group = QButtonGroup(self)
        for lvl, rb in self._load_buttons.items():
            rb.setProperty("level", lvl)
            self._load_group.addButton(rb)
            rb.toggled.connect(self._on_load_level_changed)
        self._load_buttons.get(self.ctx.settings.load_level, self.load_balanced).setChecked(True)

        self.background_priority = QCheckBox("Mit Hintergrund-Priorität laufen (immer)")
        self.background_priority.setChecked(self.ctx.settings.background_priority)
        self.background_priority.stateChanged.connect(self._on_load_level_changed)

        self._load_readout = QLabel()
        self._load_readout.setStyleSheet(f"color: {_theme_tokens()['ink_3']}; font-style: italic;")

        load_box = QVBoxLayout()
        for rb in self._load_buttons.values():
            load_box.addWidget(rb)
        load_box.addWidget(self.background_priority)
        load_box.addWidget(self._load_readout)
        self._add_field(
            f4,
            "Hintergrundlast",
            self._row_widget(load_box),
            hint="Wie sehr darf die Transkription den Mac auslasten? Höhere Stufen "
            "nutzen mehr Kerne; der Rechner bleibt responsiv.",
            hint_kind="info",
        )
        self._on_load_level_changed()  # paint the read-out
```

> Check whether `_row_widget` accepts a layout or a widget (grep its definition). If it wraps a layout, the above is correct; otherwise wrap `load_box` in a `QWidget` first, matching the existing `model_row` / `drift_row` pattern.

**Step 2: Delete the multiproc block (lines 569-583 — `self.multiproc = QSpinBox()` … its `_add_field`).** Keep the `bw` (552-562) and `fast_mode` (564-567) blocks untouched.

**Step 3: Add imports.** Ensure the top-of-file PyQt6 import block includes `QButtonGroup`, `QRadioButton`, `QCheckBox`, `QLabel`, `QVBoxLayout` (most already present — add the missing ones to the existing `from PyQt6.QtWidgets import (...)`).

**Step 4: Add the change handler + level reader** (near the other private methods, e.g. by `_schedule_save`):
```python
    def _current_load_level(self) -> str:
        btn = self._load_group.checkedButton()
        return btn.property("level") if btn else "balanced"

    def _on_load_level_changed(self, *_args) -> None:
        from core.load import describe_profile, resolve_load_profile
        from core.hw import detect
        import os

        _mem, perf = detect()
        profile = resolve_load_profile(
            self._current_load_level(),
            perf_cores=perf or (os.cpu_count() or 4),
            background_priority=self.background_priority.isChecked(),
        )
        self._load_readout.setText(f"Diese Stufe: {describe_profile(profile)}")
        self._schedule_save()
```

**Step 5: Update `_do_save`** — replace line 1052 (`s.parallel_transcribe = self.parallel.value()`) and line 1059 (`s.whisper_multiproc = self.multiproc.value()`) with:
```python
        s.load_level = self._current_load_level()
        s.background_priority = self.background_priority.isChecked()
```

**Step 6: Remove now-dead helpers** (~1148-1180): `_hw_recommendation_value`, `_hw_recommendation_hint`, `_hw_recommendation`, `_multiproc_recommendation_value`, `_multiproc_recommendation_hint`. Grep to confirm no remaining callers:
Run: `grep -n "_hw_recommendation\|_multiproc_recommendation\|self.parallel\|self.multiproc" ui/settings_pane.py`
Expected: no matches after edits.

**Step 7: Verify import + launch**

Run: `python -c "import ui.settings_pane"` → Expected: no error.

**Step 8: Commit**

```bash
git add ui/settings_pane.py
git commit -m "feat(settings-ui): Hintergrundlast level group replaces parallel/multiproc spinboxes"
```

---

## Task 7: `ui/queue_tab.py` — remove the now-meaningless tuning-hint banner

**Files:**
- Modify: `ui/queue_tab.py` (banner creation 117-128; throttle 194-201; `_refresh_tuning_hint` 210-243)

> The banner compared the user's `parallel_transcribe` against the HW recommendation — both gone now.

**Step 1: Delete the `_tuning_hint` QLabel creation block** (the comment + lines 121-128, including `self._refresh_tuning_hint()`).

**Step 2: Delete the throttle block in `_tick`** (~194-201, the `if now - getattr(self, "_tuning_hint_at", 0.0) > 60: ...`).

**Step 3: Delete the `_refresh_tuning_hint` method** (~210-243).

**Step 4: Confirm no stragglers**

Run: `grep -n "_tuning_hint\|_refresh_tuning_hint\|recommended_parallel\|recommended_multiproc" ui/queue_tab.py`
Expected: no matches.
Run: `python -c "import ui.queue_tab"` → Expected: no error.

**Step 5: Commit**

```bash
git add ui/queue_tab.py
git commit -m "refactor(queue-tab): drop HW-divergence tuning hint (obsolete under load levels)"
```

---

## Task 8: Full verification + manual smoke

**Step 1: Full unit suite + lint**

Run: `python -m pytest tests/ -q`
Expected: PASS (pre-commit also runs ruff + unit tests).

Run: `grep -rn "parallel_transcribe\|whisper_multiproc" --include="*.py" .`
Expected: only the migration helper in `core/models.py` and the legacy-migration tests reference these names.

**Step 2: Manual smoke (the load-bearing behaviour)**

Launch the app, open Settings → set **Leise**, start the queue, then in a terminal:
Run: `pgrep -fl "taskpolicy -b" ; ps -o pid,nice,command -ax | grep -i whisper-cli | grep -v grep`
Expected at **Leise**: a `taskpolicy -b … whisper-cli … -t 2` process (low/background scheduling).
Switch to **Ausgewogen** (next episode): whisper-cli launched via `nice -n 10`, `-t 4`.
Switch to **Volle Leistung** with the checkbox **on**: `nice -n 5`, two concurrent whisper-cli processes; checkbox **off**: no `nice`/`taskpolicy` prefix.
Confirm: while a transcription runs at Ausgewogen, the UI and other apps stay responsive.

**Step 3: Final commit (if any smoke fixes were needed)**

```bash
git add -A && git commit -m "fix(load): smoke-test corrections"
```

---

## Out of scope (deliberate — see design doc)

Activity/idle polling, battery/thermal auto-switching, GPU throttling (`--no-gpu`), hard CPU-% duty-cycling (SIGSTOP/SIGCONT), mid-run renice of running whisper, manual per-level override. `whisper_multiproc` stays effectively 1 (no `-p` split).
