# "Pausing" transitional queue state — Design

**Datum:** 2026-05-18
**Status:** Approved, ready for implementation plan

## Problem

`shows_tab._pause()` sets `queue_paused="1"` **and** calls
`self._thread.request_stop()`. `request_stop()` makes the worker finish
the **current episode** (whisper-cli keeps running at full CPU) and only
halts *between* episodes — it does NOT kill the in-flight job (that is the
force-Stop path). So there is a real "draining" window between the Pause
click and the queue actually halting.

Today the UI flips immediately: Queue-tab buttons go to the paused shape
and the tray status Pill still shows `running`. The user gets no signal
that "the pause is queued; the current episode is still finishing." That
is confusing and looks like Pause did nothing (CPU still pegged).

## Goal

Represent a distinct **`pausing`** state: "pause is coming, the current
episode finishes first, then the queue halts." Chosen approach (from
brainstorming, Option A): an explicit derived state surfaced as an amber
Pill + a "Pausing…" button label + statusbar text.

## State model (pure, testable)

New Qt-free helper, single source of truth for every surface:

```python
# core/queue_status.py
def queue_ui_state(*, queue_paused: bool, running: bool) -> str:
    if running and queue_paused:
        return "pausing"
    if running:
        return "running"
    if queue_paused:
        return "paused"
    return "idle"
```

Unit-tested like `check_counts_as_success` / `should_recheck_update`.
**No new persisted state** — `pausing` is derived from the existing
`queue_paused` meta + `ctx.queue.running`.

State transitions: `running` --Pause--> `pausing` --(current episode
finishes / worker exits)--> `paused` --Resume--> `running`.

## Surface 1 — Tray status block (`ui/menu_bar.py`)

- `build_tray_menu` / `_build_status_block` receive the state (or a
  `pausing: bool`).
- When `pausing`: `Pill("Pausing", kind="pausing")`; replace the
  queue-fraction subtitle with "Finishing current episode…"; keep the
  current-title line and the in-flight ETA (that ETA is now the
  meaningful number — time until the drain completes).
- Add a `kind="pausing"` (amber/orange) to the `Pill` class, mirroring
  the existing kind→colour map. Verify the exact `Pill` API during
  implementation.

## Surface 2 — Queue-tab buttons (`ui/queue_tab.py:_update_btns`)

Derive state via the helper:
- `pausing`: `pause_btn` → text "Pausing…", disabled; `start_btn`
  disabled (no Resume mid-drain — per the chosen preview); `stop_btn`
  enabled (force-Stop must stay available to abort the in-flight job).
- `paused` (after drain): existing logic (Start→"Resume" enabled, Pause
  disabled, Stop disabled).
- The 1 s `_tick` already refreshes the header/buttons, and `_pause()`
  already calls `_update_btns()` on click → instant feedback here.

## Surface 3 — Statusbar (`ui/menu_bar.py:346`)

When `pausing`, the status-bar message →
"Pausing — current episode finishes, then the queue halts."
Gate on the derived state at that call site.

## Surface 4 — Immediate cross-surface refresh on pause (critical)

The tray status block is rebuilt only on `episode_done` /
`check_done` (`app.py`). During a drain **no `episode_done` fires** until
the current episode ends, so the tray Pill would stay `running` until
then — defeating the feature. `shows_tab._pause()` must trigger an
immediate tray rebuild in `ParagraphosApp` (reuse the existing
app↔thread/shows wiring, or add a minimal `stateChanged`-style
notification) so the Pill flips to "Pausing" at click time. Queue-tab
needs nothing extra (covered by `_tick` 1 s + on-click `_update_btns`).

## Log line

Align `shows_tab._pause()`'s log with `_stop()`'s wording:
"pausing — current episode will finish, then the queue halts."

## Tests

- Unit: `queue_ui_state` truth table — all four states incl. `pausing`.
- Qt surfaces are not unit-testable headless (consistent with prior
  features in this repo) — the load-bearing logic lives in the pure
  helper; the visual is a manual smoke step.

## YAGNI / deliberate decisions

- No new persisted state — derived only.
- No "Resume cancels the pending pause during drain" affordance; the
  chosen preview keeps Resume disabled until fully drained. Revisit if
  requested.
- Reuse the existing `Pill` and the 1 s tick; the only additions are one
  amber Pill `kind`, one pure helper, and one pause-time tray-refresh
  poke.
- Force-Stop stays enabled during `pausing` so the user can still abort
  the in-flight episode immediately.
