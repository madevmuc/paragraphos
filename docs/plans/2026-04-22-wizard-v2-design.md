# First-run wizard v2 — design

**Date:** 2026-04-22
**Status:** approved, ready for implementation planning

## Problem

The current first-run wizard (`ui/first_run_wizard.py`, shipped in v1.0) has three usability flaws and one correctness bug reported by users testing on fresh Macs:

1. **Every action button is enabled at once.** A user can click Install Homebrew, Download model, `brew install whisper-cpp`, and `brew install ffmpeg` all in parallel. Two `brew install` invocations running concurrently fail because brew holds a global lock, and nothing in the wizard enforces the actual dependency order (`brew → whisper-cpp, brew → ffmpeg`).
2. **No feedback during whisper-cpp and ffmpeg install.** `_install_whisper` / `_install_ffmpeg` shell out to `brew install` in a background thread with `capture_output=True`; the UI just says `"installing…"` for 30-60 s with no further signal. Users report clicking the button and "hoping something works."
3. **No hardware compatibility check.** An Intel Mac or an ancient macOS build can reach the "everything green" state and then fail at first transcription.
4. **Dep-check misses successfully-installed whisper on non-standard brew prefixes.** `core.deps.check().whisper_cli` hardcodes `/opt/homebrew/bin/whisper-cli`, and `install_whisper_cpp()` invokes `brew` without an expanded PATH, so a Finder-launched `.app` can't find `brew` right after a fresh install.

## Goals

- Remove ambiguity about what to click, in what order.
- Give the user continuous visible signal during every step so no install phase feels hung.
- Reject Macs that cannot run the app before the user wastes time on installs.
- Fix the dep-detection regression so a successful install is reliably seen as success.

## Non-goals

- Automating the `sudo` password prompt in the Homebrew installer. macOS Terminal remains the only sanctioned channel.
- Signing / notarization changes (tracked separately).
- Custom whisper-cpp builds. Homebrew bottle stays the only supported source.

## Design

### 1. Hardware compatibility pre-check (new)

Shown as a fifth check at the top of the wizard, evaluated synchronously on open.

**Blocking** — Continue disabled, explanation shown:
- **Apple Silicon (`arm64`).** Intel Macs are rejected — whisper.cpp bottles target arm64 and CPU-only transcription on Intel is too slow to be useful for this tool's purpose.
- **macOS ≥ 13.0 (Ventura).** PyQt6 6.7 wheels and current whisper-cpp bottles both assume this floor.

**Advisory** — yellow pill, Continue stays enabled, tooltip explains:
- **RAM ≥ 8 GB.** large-v3-turbo needs ~2 GB resident; below 8 GB will swap heavily.
- **Free disk ≥ 3 GB.** Homebrew (~400 MB) + whisper-cpp + ffmpeg + model (1.5 GB) + headroom.

Detection lives in a new `core/compat.py` module with a `check_compat() -> CompatStatus` helper, mirroring the shape of `core/deps.py::check()`.

### 2. Installer flow — auto-start what's safe, serialize what must be

**On wizard open (no user click):**
- Model download starts immediately. No sudo, no brew dependency, pure HTTPS.
- Progress bar renders as today.

**Homebrew row remains a user click** — launching Terminal with a sudo prompt is an explicit, consequential action and auto-starting would be jarring. Button label: `"Install Homebrew…"`. Sub-copy: `"Opens Terminal. Enter your Mac password when prompted."`

**whisper-cpp and ffmpeg auto-chain after brew is detected:**
- Both rows start in a new `waiting` state with sub-copy `"waiting for Homebrew"`, no action button shown.
- When `deps.check().brew` flips to true (on Recheck or on the next poll tick), the wizard fires `brew install whisper-cpp` automatically.
- When whisper-cpp flips to true, the wizard fires `brew install ffmpeg` automatically.
- The user never clicks anything between Homebrew and Continue.

### 3. Live feedback during brew installs

Replace `subprocess.run(capture_output=True)` with `subprocess.Popen(stdout=PIPE, stderr=STDOUT, text=True)` plus a daemon reader thread. Each stdout line is emitted through a Qt signal to the wizard.

Each running row renders:
- **Primary status (pill):** `"installing… 23s"` — elapsed counter driven by a 1 Hz QTimer.
- **Sub-line:** the latest stdout line from brew, truncated to ~80 chars — e.g. `"Pouring whisper-cpp-1.7.5.arm64.bottle.tar.gz"`. Small grey text.

The elapsed counter is the primary reassurance that the process is alive; the stdout line is the secondary "and this is what it's doing right now" signal. This matches option C from the brainstorm — both, not one or the other.

### 4. Bug fixes folded into the same change

- **`core.deps.check().whisper_cli`** — switch from hardcoded `Path(WHISPER_BIN).exists()` to the multi-path `_has_any(candidates, "whisper-cli")` pattern that brew/ffmpeg already use. Candidates: `/opt/homebrew/bin/whisper-cli`, `/usr/local/bin/whisper-cli`, `/opt/local/bin/whisper-cli`.
- **`install_whisper_cpp()` / `install_ffmpeg()`** — run `brew` with an explicit `env` whose PATH prepends `/opt/homebrew/bin:/usr/local/bin:/opt/local/bin`, so a `.app` inheriting Finder's minimal PATH can still resolve `brew` immediately after a fresh install without needing a restart.

### 5. UI states — state machine per `StepRow`

| State | Pill | Sub-copy | Action button |
|---|---|---|---|
| `idle` | `"checking…"` neutral | `""` | hidden |
| `waiting` | `"waiting"` neutral | `"waiting for Homebrew"` | hidden |
| `running` | `"installing… Ns"` running | latest brew stdout line | hidden (disabled while running) |
| `ok` | `"ok"` green | `""` | hidden |
| `fail` | `"fail"` red | last error line | `"Retry"` |

`StepRow.set_waiting(reason)` is new. `set_running` gains a `sub_line_updater` API the install thread calls on each stdout line.

## Architecture

- **New:** `core/compat.py` — hardware/OS compatibility detection, mirrors `core/deps.py` shape.
- **Modified:** `core/deps.py` — multi-path whisper detection, PATH-aware brew invocations.
- **Modified:** `ui/first_run_wizard.py` — auto-start model download on open, waiting state for whisper/ffmpeg, auto-chain after brew, live stdout sub-line, hardware check row.
- **New:** `ui/install_runner.py` (or fold into wizard) — `Popen`-based brew runner that emits a Qt signal per stdout line and a final exit-code signal.

Wizard still exits Accepted only when all four deps + compat are OK, same as today.

## Testing

- **Unit** (`tests/test_compat.py`, new): mock `platform.machine()` / `platform.mac_ver()` / `psutil.virtual_memory()` / `shutil.disk_usage()` to verify each blocking and advisory classification.
- **Unit** (`tests/test_deps.py`, new): table-driven test for `_has_any` resolving whisper-cli from each of the three candidate prefixes; assert `install_whisper_cpp` passes an env with the expanded PATH.
- **Manual smoke** on a fresh Mac: fresh user account with nothing installed → wizard auto-starts model download, user clicks Install Homebrew, whisper + ffmpeg auto-chain, Continue enables, first transcription runs. Record a short clip for CHANGELOG.

## Out of scope for this pass

- Cancelling an in-progress brew install (rare; we can add `subprocess.terminate()` later if needed).
- Offline install bundle. Internet is assumed.
- Localising wizard copy (English only).

## Next step

Hand off to `superpowers:writing-plans` to produce a step-by-step implementation plan for subagent-driven execution.
