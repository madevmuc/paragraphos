# Handoff: Paragraphos UI Refresh

## Overview

This handoff is a **targeted UI revision** of the existing Paragraphos app (PyQt6 desktop client for local podcast → whisper.cpp transcription). It covers **9 screens** — one picked variation per design question explored in the mockups. The core data model, workers, CLI, and state machine do **not** change; this is a view-layer rework.

**Target files (existing in codebase):**

| Screen | Existing file |
|---|---|
| Shows B — sidebar + table + filter popover | `paragraphos/ui/shows_tab.py` + `main_window.py` (new sidebar) |
| Queue B — hero dashboard | `paragraphos/ui/queue_tab.py` |
| Failed A — flat table with per-row menu | `paragraphos/ui/failed_tab.py` |
| Settings A — in-tab scroll + recommendation hints | `paragraphos/ui/settings_pane.py` |
| First-run A — dep checklist | `paragraphos/ui/first_run_wizard.py` |
| Add podcast A/B/C (keep all 3 as modes) | `paragraphos/ui/add_show_dialog.py` |
| Show details A | `paragraphos/ui/show_details_dialog.py` |
| Menu-bar tray B — live count icon | `paragraphos/ui/menu_bar.py` |

## About the design files

The `design_reference/` folder contains **HTML/React wireframes**, not production code. They show the intended layout, content, and information density. Your job is to **recreate these designs inside the existing PyQt6 codebase**, using the widgets, signals, and patterns already in place. Do not introduce React, Electron, or a web-view — Paragraphos is a native PyQt6 app and should stay one.

Open `design_reference/index.html` in a browser and toggle the Tweaks panel to flip between "sketchy" and "clean" modes. The **clean mode** (Inter + IBM Plex Mono, subtle borders) is the reference. Sketchy mode is exploration-only.

## Fidelity

**Mid-fidelity.** Final layout, hierarchy, exact copy, and information structure are locked. Colors are indicative (ochre accent `#b47a3a` maps loosely to PyQt's existing palette — keep the current native-macOS palette where possible, only use accent where the design calls for a highlight). Typography is descriptive (labels, sizes, monospace-vs-proportional) — respect the existing Qt system font.

Do not reproduce the HTML pixel-for-pixel. Reproduce the **structure, copy, and interaction model**.

---

## Design tokens

These are the only visual tokens the redesign introduces beyond today's palette:

| Token | Value | Usage |
|---|---|---|
| accent | approximately `#b47a3a` (ochre/clay) — **prefer an existing Qt palette role** | selected nav item, primary button, progress bar fill, "installed" checkmark |
| accent-tint | accent at ~12% opacity | selected-row background, running-state pill background |
| danger | existing Qt danger/red | failed pills, error log lines |
| ok | existing Qt success/green | ✓ installed, feed-ok pills |
| line | 1.5px solid, palette(mid) | card borders |
| line-soft | 1px solid, palette(mid) at 50% | table row dividers |
| radius-sm | 5–6 px | pills, inputs |
| radius-md | 8–10 px | cards, dialogs |
| mono font | existing: Menlo/Monaco | all numbers, slugs, timestamps, file paths |

**Spacing scale:** 4, 6, 8, 10, 12, 14, 18 px. Don't invent new values.

**Typography:**
- Body: 13 px, system font
- Small: 12 px (table cells, captions)
- Tiny: 11 px muted (hints, sub-labels)
- Heading (section title): 14 px bold
- Dialog title: 14 px bold
- Uppercase mini-label (stat boxes, section dividers): 10 px, 600 weight, letter-spacing 0.5, muted

---

## Screens

### 1. Shows — Variation B (sidebar + table + filter popover)

**Reference:** `design_reference/index.html` → Shows tab → middle column ("B · Sidebar + cards").
Screenshot: `_screens/01-shows.png`.

**Structure:**
- **Left sidebar (160 px wide, full height):** replaces today's top tab bar. Groups labelled "Library" and "System".
  - Library → Shows (count 16, active), Queue (count 23 = pending), Failed (count 4), All episodes
  - System → Settings, Logs, About
  - Active item: accent-tint background, 500 weight. Counts right-aligned in `.count` chips.
- **Right pane (flex 1, padding 14):**
  1. **Library stats header** — keeps today's rich-text label ("Library — N transcripts · Xh of audio · Y words · Z pending · N failed"). Unchanged from `shows_tab._update_global_stats`.
  2. **Filter toolbar row** (new):
     - Left: muted tiny text summarising active filters, e.g. `Showing 7 of 16 · filtered by enabled, feed:ok`.
     - Right: `▾ Filter` button with a small accent pill showing active-filter count (e.g. `2`).
     - Clicking opens a **filter popover** (220 px wide, anchored below the button):
       - Checkbox group: `☐ Enabled only`, `☐ Has pending episodes`, `☐ Has failed episodes`
       - Uppercase mini-label "Feed status" — checkboxes for `✅ ok`, `⚠ stale`, `✖ unreachable`
       - Uppercase mini-label "Search" — text input
       - Footer row: ghost "Clear" / primary "Apply"
     - State lives on `ShowsTab`; applied filters mutate the table query in `ShowsTab.refresh()`.
  3. **Table** — same columns as today's shows_tab, but re-ordered and re-styled:
     - On (40 px) — `●` if enabled, dim `○` if disabled
     - Title (stretch) — two-line: `title` (500 weight) over `slug` (mono tiny muted)
     - Progress (90 px) — `done/total` mono tiny above a `Progress` bar (use existing Qt progress widget, or a styled `QFrame`)
     - Pending (70 px) — mono tiny
     - Feed (70 px) — `Pill` widget: "ok" (accent-tint + accent fg) or "stale" (red-tint + danger fg). Fill on `_check_feed_health`.
     - Double-click opens `ShowDetailsDialog` (existing behaviour, keep it).
  4. **Button row (flex, gap 6):**
     - primary: `+ Add podcast`
     - `Add episodes`, `Check now`
     - spacer
     - ghost: `Check feeds`, `Rescan library`
     - Wire to existing handlers (`_add`, `_curated`, `_check`, `_check_feed_health`, `_rescan_library`).

**Removed vs today:** top tab bar (moved to sidebar), "Stop" / "Pause" buttons (moved to Queue tab — they belong with the run UI).

**Pill widget** — introduce a reusable `Pill` helper (QLabel with styled background):
- `kind="ok"` → accent-tint bg, accent fg
- `kind="fail"` → rgba(200,80,80,.15) bg, danger fg
- `kind="running"` → accent bg, white fg
- `kind="idle"` / default → palette(alternate-base) bg, muted fg

---

### 2. Queue — Variation B (hero dashboard)

**Reference:** `design_reference/index.html` → Queue tab → middle column.
Screenshot: `_screens/02-queue.png`.

**Structure:**
- **Sidebar active item:** "Queue" (highlighted).
- **Main pane:**
  1. **Hero card** (border 1.5px, radius 10, padding 16) — only shown when a run is active. Layout: 2-column grid with `auto 1fr` columns, gap 18, centered.
     - **Left column:** 110 × 110 circular progress ring. Stroke 4 px. Right + bottom quadrants in `line-soft`, left + top in `accent`. Centered inside: `3/12` mono 22 px 700, then `25%` tiny muted below.
     - **Right column:**
       - Top row: `Pill[running]` + `b[ odd-lots · The weird cargo-ship market ]` + spacer + `Pause` + `Stop` buttons.
       - **4-column stats grid** (gap 14):
         - `STARTED` · `09:14` · `Mon · Apr 20, 2026`
         - `ELAPSED` · `18m 02s`
         - `PER EP.` · `4m 31s` · `(est. 5m 40s)`
         - `FINISH ≈` · `10:24` · `Mon · in 52m — before lunch`
       - Each stat is a uppercase mini-label (10 px, 600, letter-spacing 0.5, muted) above a mono 15 px 600 value, with optional tiny muted sub-line.
       - **Crucial detail** (per teammate review): date lines must include **day-of-week + date**, and finish-time sub-line should include a **human framing** ("in 52m — before lunch") when that framing fits the day. When no frame applies, show just `Mon · in 52m`.
  2. **Pending/in-flight table** (below the hero, stretch) — same columns as today's queue_tab (`Show`, `Title`, `Status`) but minus the "Pub Date" and "Ep#" columns that are never useful during a run. Keep same query (`status IN ('pending','downloading','downloaded','transcribing')`).
  3. **When idle** (no run active): hide the hero card entirely, keep only the "Queue — pending: N · done: N · failed: N · idle" header from today's `_format_header`, but styled as the library stats label. Button row below: primary `Start`, `Pause` (disabled), `Stop` (disabled), ghost `Refresh`.

**Derived values** — every number on the hero comes from what `queue_tab.py` already computes:
- `3/12` ← `self._done / self._total`
- `started` ← `_started_at` (format with `_fmt_dt_locale`, then append day + date — use `%a · %b %d, %Y`)
- `elapsed` ← `now - _started_at`
- `per ep.` → show live avg if `_episode_durations`, else the historical est (keep today's `live_avg || ctx.queue.effective_avg_sec` logic). Label changes between `avg/ep` and `est/ep`.
- `finish ≈` ← `now + avg * remaining`. The "human framing" is new — compute it as follows:
  - `< 30m` → "soon"
  - finish before noon → "before lunch"
  - finish 12–14 → "around lunch"
  - finish 14–17 → "this afternoon"
  - finish 17–20 → "this evening"
  - finish next day → "tomorrow morning" / "overnight"
  - else → omit the framing, just show `in Xm`

**Per-row progress detail** — the B variant uses a compact table, but the teammate feedback on A ("more detailed information line like C") should also apply here: each in-flight row's Status cell should render a pill like `transcribing · 62%` or `downloading · 18%`, and a mono tiny muted second line under the title: `whisper · seg 44/71 · 4m 12s elapsed · ~2m 38s left` / `mp3 · 42 / 238 MB · 8.2 MB/s · ~24s left`. For pending rows, show `queued · waiting — position N of M`. For done rows (if rendered in a "recent" section): `done · 5m 12s · 8 742 words · 09:18`.

These sub-strings are **already available**: download progress is emitted by the worker; whisper segment count comes from `whisper.cpp` stderr. Where the numbers aren't currently surfaced, the worker thread will need to emit new `progress_detail` signals — not in scope of this design, but the UI slots are ready.

---

### 3. Failed — Variation A (flat table)

**Reference:** `design_reference/index.html` → Failed tab → left column.
Screenshot: `_screens/03-failed.png`.

**Structure:**
- Sidebar active item: "Failed".
- Main pane:
  1. **Table** (border 1.5px, radius 6, stretch):
     - Columns: `Show` (mono tiny) · `Episode` (stretch, 500 weight) · `Reason` (tiny, danger color) · `Tries` (60 px mono tiny) · `Last attempt` (140 px mono tiny muted) · action dots `⋯` (28 px)
     - The `⋯` cell opens a per-row context menu: `Retry`, `Mark resolved`, `Show log`, `Copy error`, `Skip forever`.
     - Alternate: the whole row can be right-click-menu'd (same actions) — keep today's `QTableWidget.customContextMenuRequested` pattern.
  2. **Button row:**
     - `Retry selected` (enabled when ≥1 row selected)
     - `Mark resolved` (same)
     - spacer
     - ghost `Export .log`

**Reason strings** — use the existing Python exception types but **humanize**:
- `whisper.cpp: ggml_new_tensor` → `whisper: ggml_new_tensor` (keep technical — users debugging this need the real string)
- `SSRFGuardError` → `ssrf-guard: private IP`
- `FileTooLargeError` → `mp3 > 2GB cap`
- `HashMismatch` → `model hash mismatch`

**Selection behaviour:** full-row select, multi-select enabled.

---

### 4. Settings — Variation A (in-tab scroll, auto-save, recommendation hints)

**Reference:** `design_reference/index.html` → Settings tab → left column.
Screenshot: `_screens/04-settings.png`.

**Structure:** unchanged from today's `settings_pane.py` **except** — every field now has an **optional inline recommendation/tip line** below it. This is the main update.

**Field rendering pattern:**

Two-column grid, `150px 1fr`:
- Col 1 (label): muted tiny, right-aligned, 6 px top padding.
- Col 2 (value): the input widget itself, then — if a hint is defined — a tiny line below with:
  - Prefix glyph: `✓` (green, accent color) for **validated recommendations** ("recommended: 2 (16 GB RAM detected)"), `ⓘ` (muted, italic) for **tips/info** ("Cap at ~20 Mbps if you share Wi-Fi").
  - Italic where kind=info, upright where kind=good.
  - Line-height 1.35, margin-top 3 px.

**Exact hint copy per field:**

| Section | Field | Value shown | Hint kind | Hint copy |
|---|---|---|---|---|
| Library & output | Output root | `~/wiki/raw/podcasts` | info | `markdown transcripts land here, one folder per show` |
| Library & output | Obsidian vault | path + name row | info | `auto-fills vault name from folder ("wiki")` |
| Schedule & monitoring | Daily check time | `09:00` | info | `runs in the background — Mac must be awake` |
| Schedule & monitoring | Catch-up missed runs | checkbox | good | `recommended — runs immediately on wake if a check was missed` |
| Notifications | Notify on success | checkbox | info | `if silent: re-enable in macOS → Notifications` |
| Transcription engine | Whisper model | combobox + `● installed` badge (existing) | good | `best accuracy/speed balance on Apple Silicon — recommended` |
| Transcription engine | Parallel workers | spinbox | good | `recommended: N  (X GB RAM, Y perf cores detected)` — dynamic, see `_hw_recommendation()` — **extend it** so it returns just the number string "2 (16 GB RAM, 8 perf cores detected)"; the UI wraps it with "recommended: " |
| Transcription engine | Bandwidth limit | spinbox | info | `0 = unlimited. Try 20 Mbps if shared Wi-Fi starts hitching` |
| Storage & retention | MP3 retention | spinbox | info | `transcripts are kept forever — only the audio is purged` |
| Storage & retention | Delete MP3 after transcribe | checkbox | info | `turn on to save ~40 GB/yr if you never re-play audio` |
| Storage & retention | Log retention | spinbox | info | `enough to debug any failed run` |

The existing **"Automation & remote control"** section (terminal help + agent prompt) stays as-is at the bottom.

**The auto-save indicator** ("✓ saved at 09:14:23") stays at the bottom of the form — don't move it.

Keep the `QScrollArea` wrapper — this is a long form.

---

### 5. First-run wizard — Variation A (dep checklist)

**Reference:** `design_reference/index.html` → First-run tab → left column.
Screenshot: `_screens/05-first-run.png`.

**Structure:** modal dialog, 520 px wide.
- Title: `Paragraphos — First-run setup`
- Heading: `Welcome to Paragraphos` (h3)
- Sub-copy (muted tiny): `Everything runs locally. We need a few tools on your Mac before the first run.`
- Body: vertical stack of dep rows, each separated by 1 px line-soft bottom border, 6 px top/bottom padding:
  - Label (flex 1, 500 weight, 13 px): e.g. `Homebrew`, `whisper-cpp`, `ffmpeg`, `large-v3-turbo (1.5 GB)`
  - Right-aligned status:
    - If installed: `Pill[ok]` with text `✓ installed`
    - If in progress: 140 px progress bar + mono tiny percent (e.g. `62%`)
    - If not yet started: muted tiny `not installed — will download on start`
- Footer row (margin-top 16, justify flex-end):
  - ghost `Cancel`
  - primary `Continue to Paragraphos` — **disabled until all deps report `ok`**

**Behaviour** — keep today's sequencing: check brew → check whisper-cpp → check ffmpeg → download model. Update rows in-place as each finishes. Re-running the wizard after cancel must re-check all four, not assume state.

---

### 6. Add podcast — Variations A, B, C (keep all three as modes)

**Reference:** `design_reference/index.html` → Add / Details / Tray tab → top "Add podcast dialog" section.
Screenshot: `_screens/06-add-details-tray.png`.

Keep all three as **three modes** of one dialog, selectable via a segmented control at the top of `AddShowDialog`:

- **[ By name ] [ By URL ] [ Paste Apple link ]**
- Default mode: **By name** (A).

**Mode A — "By name" (search + form):**
- Input: `Name or URL`, placeholder `e.g. Odd Lots`
- Primary `Search` button → calls iTunes Search API (existing code path).
- Results list (max 140 px, scroll, 1.5 px border radius 6): each row `NAME — PUBLISHER`, row background accent-tint when selected.
- Once a result is picked, expand the form below:
  - `Slug` (editable text, prefilled by slug-ifying title)
  - `Title`
  - `RSS` (mono tiny)
  - `Backlog` (combobox): `All`, `Only new from now` *(default)*, `Last 20`, `Last 50`
  - `Whisper prompt` (multi-line textarea, min 54 px) — prefill with auto-generated prompt from show metadata
- Footer: ghost `Cancel`, primary `Save`.

**Mode B — "By URL" (rich preview):**
- Input: RSS URL.
- On blur / Fetch button: the dialog **rewrites itself** to show a preview:
  - 72×72 artwork placeholder (load from podcast `<itunes:image>` if available)
  - Title (15 px 600) + `publisher · host1, host2` (tiny muted) + `N episodes · latest YYYY-MM-DD` (mono tiny)
  - `Callout`: `We auto-generated a whisper prompt from the last 20 episode titles — edit if needed.` (yellow/ochre accent sticky-note style)
  - `Whisper prompt` as a framed editable block (border 1.5, radius 6, padding 8) with uppercase mini-label `Whisper prompt` above.
  - **Backlog** rendered as a **segmented control** (not a dropdown): `[ All ] [ Only new ] [ Last 20 ] [ Last 50 ]` — "Only new" selected by default. Segment active state: accent bg, white fg.
- Footer: ghost `Cancel`, primary `Save & start` (triggers a Check immediately after adding).

**Mode C — "Paste Apple link" (one-step):**
- Input: `Paste a feed URL or podcast link`, mono style, 13 px.
- Callout below: `We'll follow the Apple link → find the RSS → build a preview`
- After paste + auto-detect, show a dashed-bordered auto-detected card (border 1.5 dashed line-soft, radius 6, padding 10):
  - Row: `<title>` (b tiny) + `<ep_count> eps · <feed_host>` (mono tiny muted) on separate lines, right: `Pill[ok] feed ok`
- Footer: ghost `Cancel`, `Customise…` (switches to mode A with fields pre-filled), primary `Add` (adds with defaults: Only new backlog, auto prompt).

**Shared dialog behaviour:**
- Width: 540 px.
- Esc cancels, Enter triggers primary action.
- All three modes result in the same `Show` being appended to `watchlist.yaml` via the existing `_do_save` path.

---

### 7. Show details — Variation A (single sheet, only variant)

**Reference:** `design_reference/index.html` → Add / Details / Tray tab → "Show details" section.

**Structure:** modal dialog, 620 px wide, min-height 440 px. Same surface as `ShowDetailsDialog`, restyled.
- **Header row** (margin-bottom 12):
  - 64×64 artwork placeholder (load from show metadata)
  - Title (15 px 600), then `slug · N eps · N done · N pending` (tiny muted), then feed URL (mono tiny muted)
  - Right-aligned: feed health `Pill` (`ok` / `stale` / `unreachable`)
- **Form grid** (`120px 1fr`, gap 6 × 10, font 12):
  - `Enabled` — toggle (●/○) mapped to `show.enabled`
  - `Whisper prompt` — multi-line editable (sk-box style, min-height 40)
- **Recent episodes table** (margin-top 12, max-height 140, scroll, border 1.5 radius 6): last 10 episodes:
  - `YYYY-MM-DD` (80 px, mono tiny muted) · title (stretch) · status `Pill` (`done`/`failed`/`pending`)
- **Footer row** (justify flex-end):
  - ghost `Remove` (confirm dialog) — removes from watchlist
  - `Mark all stale` — calls `_mark_stale(slug)` (existing)
  - primary `Save`

**Wiring:** reuses everything in today's `ShowDetailsDialog` — only the layout/spacing changes.

---

### 8. Menu-bar tray — Variation B (live count icon)

**Reference:** `design_reference/index.html` → Add / Details / Tray tab → "Menu-bar tray" section, middle column.

**Icon behaviour:**
- **Idle:** monochrome `P` glyph (20 px, 1.5 px stroke), matches today.
- **Running:** glyph replaced by **live progress fraction** rendered as text inside the icon — e.g. `3/12`. Use `QSystemTrayIcon.setIcon()` with a dynamically-rendered `QPixmap` (draw the fraction with `QPainter` at macOS tray-icon size, 22×22 @1x / 44×44 @2x).
  - Text size: 10 px, 700 weight, black in light menu bar / white in dark.
  - Update on every `episode_done` signal from the worker thread.
- **Done (just finished):** briefly show `✓` for 5 seconds, then revert to `P`.

**Menu contents:**

When a run is **active**, the first menu item is a **rich non-interactive status block** (add via `QWidgetAction`):
- Row 1: `Pill[running]` + `b "3/12"` + spacer + `mono "ETA 52m"`
- Row 2: progress bar (full width of menu, ~260 px, accent fill, 6 px tall, radius 3)
- Row 3: muted tiny: `Now: odd-lots — The weird cargo-ship market…` (truncate at menu width)
- Then a separator, then: `Open window`, `Pause`, `Stop`.
- Separator, then: `Import OPML…`.
- Separator, then: `Quit`.

When **idle**:
- `Open window ⌘O`
- `Check now ⌘R`
- Separator, `Import OPML…`
- Separator, `Quit ⌘Q`

Menu width: minimum 280 px so the active-run block breathes.

**Wire-up:** today's `menu_bar.py` already has `on_queue_sized`, `on_episode_done`, `on_finished_all` signals from the worker. The icon updater is the only new piece — a small `IconRenderer` class that takes `(done, total, running)` and returns a `QIcon`.

---

## Interactions & behavior (cross-cutting)

### Sidebar nav (Shows/Queue/Failed + Settings/Logs/About)
- Clicking an item swaps the right-pane widget (use a `QStackedWidget`).
- Counts update live: subscribe to the same signals the queue tab uses (`queue_sized`, `episode_done`, `finished_all`).
- Active item: accent-tint background, 500 weight label.
- Counts render as right-aligned chips, mono 11 px.

### Pill component
Implement as `QLabel` subclass or styled `QLabel` with `setObjectName("Pill")` and QSS variants. Kinds: `ok`, `fail`, `running`, `idle`.

### Progress bar
Two flavours:
1. Standard thin bar (4–6 px tall, radius 3) — use for row progress and menu-bar progress.
2. Circular ring — use only in the Queue hero. Draw with `QPainter` in a custom `QWidget`.

### Auto-save (Settings)
Keep the existing `QTimer` debounce (250 ms). Surface the "✓ saved at HH:MM:SS" label bottom-left of the form. Don't use a toast or dialog.

### Filter popover (Shows)
Built with `QMenu` or a frameless `QWidget` popup anchored to the filter button. Persist filter state in `QSettings` so it survives restart.

---

## State management

All state lives in existing models (`AppContext`, `Watchlist`, `StateDB`, `QueueState`). New UI-only state:

- `ShowsTab`: `active_filters: dict` — keys `enabled_only`, `has_pending`, `has_failed`, `feed_ok`, `feed_stale`, `feed_unreachable`, `search_text`. Persisted via `QSettings`.
- `QueueTab`: no new state; all values derived.
- `SettingsPane`: no new state; hints are static copy.
- `TrayIcon`: `_last_tooltip_text`, `_is_running` — transient, not persisted.

---

## Files

### Design references (bundled)
- `design_reference/index.html` — entry point, open in browser
- `design_reference/app.jsx` — top-level page router (the in-browser tab bar)
- `design_reference/components.jsx` — shared UI helpers (MacWindow, Pill, Progress, Callout, NavTabs, etc.)
- `design_reference/styles.css` — design tokens + helpers (match these against your QSS)
- `design_reference/wireframes_shows.jsx` — Shows A/B/C
- `design_reference/wireframes_queue.jsx` — Queue A/B/C
- `design_reference/wireframes_other.jsx` — Failed, Settings, First-run, Add, Details, Tray
- `design_reference/wireframes_final.jsx` — a single "Final" tab mixing the picked variants (for reference only)
- `design_reference/frames/` — any frame scaffolding used by `components.jsx`

### Screens
- `_screens/01-shows.png` — Shows page (all three variants side-by-side; **B is in the middle**)
- `_screens/02-queue.png` — Queue page (**B in the middle**)
- `_screens/03-failed.png` — Failed page (**A on the left**)
- `_screens/04-settings.png` — Settings page (**A on the left**)
- `_screens/05-first-run.png` — First-run (**A on the left**)
- `_screens/06-add-details-tray.png` — Add dialog (A, B, C stacked at top), Show details (single, middle), Tray (three variants at bottom; **B in the middle**)

### Existing Paragraphos files to modify
- `paragraphos/ui/main_window.py` — add `QStackedWidget` + sidebar nav; remove top tab bar
- `paragraphos/ui/shows_tab.py` — add filter toolbar row + popover; restyle table
- `paragraphos/ui/queue_tab.py` — build the hero card (new `QueueHeroWidget`); keep `_format_header` logic, render it as the stat grid
- `paragraphos/ui/failed_tab.py` — mostly unchanged; confirm columns match
- `paragraphos/ui/settings_pane.py` — extend each form row with an optional hint line (introduce a `_add_field(label, widget, hint=None, hint_kind='info')` helper)
- `paragraphos/ui/first_run_wizard.py` — restyle rows; ensure Continue stays disabled until all ok
- `paragraphos/ui/add_show_dialog.py` — add segmented control + branch to three sub-forms
- `paragraphos/ui/show_details_dialog.py` — restyle; add artwork cell
- `paragraphos/ui/menu_bar.py` — add `IconRenderer`; expand menu with `QWidgetAction` status block

### New files to add
- `paragraphos/ui/widgets/pill.py` — `Pill(QLabel, kind)` reusable badge
- `paragraphos/ui/widgets/progress_bar.py` — thin styled progress bar (if today's `QProgressBar` styling is insufficient)
- `paragraphos/ui/widgets/progress_ring.py` — circular ring for Queue hero
- `paragraphos/ui/widgets/sidebar.py` — vertical nav list with counts
- `paragraphos/ui/widgets/filter_popover.py` — the Shows filter popover

---

## Implementation order (suggested)

1. **Widgets first** (`pill`, `progress_bar`, `sidebar`) — everything else depends on these.
2. **Sidebar nav swap** in `main_window.py` — unlocks visual review of every tab.
3. **Settings hints** — isolated, low-risk, high-value.
4. **Shows filter** — new logic but contained.
5. **Queue hero** — most visible change; requires the `progress_ring` widget.
6. **Failed restyle** — cosmetic.
7. **Dialogs** (Add A/B/C, Show details, First-run) — batch them.
8. **Tray icon renderer** — last; needs cross-platform testing.

## Notes for Claude Code

- **Keep all existing signals, slots, and state-DB calls.** This is a view refresh, not a refactor. If you find yourself editing `core/` files, stop and re-read the brief.
- **Do not introduce new dependencies.** Everything should be PyQt6 + the stdlib.
- **Prefer composition over QSS gymnastics.** Custom `QWidget` subclasses for Pill, ProgressRing, etc., are cleaner than CSS-selector-heavy stylesheets.
- **Test on macOS 14+.** The tray icon dark-mode detection in particular needs a real menu-bar to verify.
