# Workspace + Library — Design

**Date:** 2026-04-23
**Status:** Brainstorm approved.
**Target:** ships as a sequence of small commits behind no flag.

A two-part change to the sidebar: rename the existing `Library` group to
`Workspace`, and add a new top-level `Library` page that browses every
completed transcript by show.

---

## Sidebar rename

```
Workspace                ←  was 'Library'
  Shows
  Queue
  Failed
Library                  ←  NEW
System
  Settings
  Logs
  About
```

`Library` lives between `Workspace` and `System`. It's a leaf entry, not
a group. Existing keyboard shortcuts / menu wiring unchanged.

---

## Library page

Three resizable horizontal panels driven by `QSplitter(Qt.Horizontal)`:

```
┌────────────┬────────────────────────┬──────────────────────────┐
│ Shows tree │ Episode list           │ Preview                  │
│            │                        │                          │
│ All eps(N) │ Date  Title  Source ⋯  │ <header strip>           │
│ • show 1   │ 2026-04-22  Ep. 88 ▶   │  Title — Show, 2026-…    │
│ • show 2   │ 2026-04-21  Ep. 87 🎙  │  [Open .md] [Reveal] [⋯] │
│ • show 3   │ ...                    │ ─────────────────────    │
│ ...        │                        │ <rendered .md transcript>│
└────────────┴────────────────────────┴──────────────────────────┘
```

All three panels:

- Full height of the window content area.
- Splitter handles are draggable.
- Widths persisted via `QSettings` under `library/splitter`.
- A right-click on the header section of the splitter reveals "Reset
  panel widths" — same pattern as the resizable-columns design.

### Tree (left)

- Top node: **All episodes** (pseudo-show; lists everything).
- One child node per show, alphabetical, with `(N)` count chip.
- Tiny icon next to each show: `🎙` for `source=podcast`, `▶` for
  `source=youtube`.
- Selection drives the episode list filter.

### Episode list (middle)

- `QTableWidget` with columns: `Date · Title · Source · Show`.
- The `Show` column hides when a specific show node is selected; it
  shows under "All episodes".
- Sort: newest `pub_date` first.
- Source-of-truth: `state.sqlite WHERE status='done'`, left-joined to
  `LibraryIndex` for the on-disk `.md` path. Rows whose `.md` is
  missing on disk are skipped (deleted file = removed from view).
- Tiny `QLineEdit` search box above the table: substring match on title
  (case-insensitive). 250 ms debounce.
- Click behaviour:
  - Single click → select. The preview pane (right) updates.
  - Double-click → opens the `.md` with macOS default app
    (`subprocess.run(["open", path], check=False)`).
- Right-click context menu:
  - **Open transcript** (`.md`)
  - **Open subtitles** (`.srt`)
  - **Reveal in Finder** — `subprocess.run(["open", "-R", path])`
  - **Open With…** — opens the macOS app-chooser via
    `subprocess.run(["open", "-a", "Finder", path])`-style fallback IF
    no NSWorkspace API is reachable from PyQt; the canonical path is
    AppKit's `NSWorkspace.shared().open(...)` which silently uses the
    default app, plus a separate "Choose Application…" via
    `subprocess.run(["open", "--reveal"])` chain. **Cleanest cross-Qt
    implementation: shell out to `open -a "Finder" "$path"` won't show
    the picker; use `osascript -e 'tell application "Finder" to open
    file POSIX file "<path>" using {choose application}'` for the
    chooser dialog.** See "Open With…" subsection below for the
    decided invocation.
  - (separator)
  - **Copy file path**
  - **Copy show slug**
  - (separator)
  - **Re-transcribe this episode** — mirrors the Show Details menu;
    calls `ui.retranscribe.retranscribe_episode(ctx, guid)`.

### Preview (right)

- Header strip:
  - Title (large, bold), show name + date underneath in muted text.
  - Source pill (`▶ YouTube` / `🎙 Podcast`).
  - Three buttons: **Open .md** · **Reveal in Finder** · **Open With…**
    — same actions as the right-click menu, surfaced for discoverability.
- Body: `QTextBrowser` with `setMarkdown(file_contents)`. Read-only.
  Wikilinks / external links open in the default browser via
  `setOpenExternalLinks(True)`.
- Empty state (no selection): muted "Select an episode on the left."
- File too big (`.md` > 5 MB): show "Transcript is large — preview
  truncated" + first 500 KB only. Opening in default app still works.

---

## "Open With…" — decided implementation

macOS provides three viable paths for the chooser:

1. **`open -R <path>`** — reveals in Finder (no chooser, just selects).
   *Used for "Reveal in Finder"*.
2. **`open <path>`** — opens with the registered default app for the
   extension (always succeeds; falls back to TextEdit for unknown
   types). *Used for "Open transcript"*.
3. **AppleScript via `osascript`**:
   ```
   tell application "System Events" to ¬
     do shell script "open -a \"$(osascript -e 'choose application' \
       | sed 's/.*://;s/[^A-Za-z0-9 ].*//')\" \"<path>\""
   ```
   That's brittle. **Cleanest in practice:** trigger AppKit's
   `NSWorkspace` "Open With…" sheet by invoking `open` with no `-a`
   AND no default registered. macOS handles the chooser automatically
   in that case.

Decided **decision tree** for "Open With…":

1. Probe macOS for the default app for the file's UTI via
   `mdls -name kMDItemContentTypeTree -name _kMDItemDefaultOpenWithApp`.
2. If a default exists → call AppleScript with `choose application`,
   capture the picked app, then `open -a "<picked>" "<path>"`.
3. If no default exists → `open` with no `-a` will already invoke the
   chooser sheet on macOS. Just `subprocess.run(["open", path])`.

Implementation lives in a single helper `core.macopen.open_with_chooser(path: Path) -> None`.
Two-line callers everywhere else.

### Why a helper module?

Reusable from the right-click menu, the preview header buttons, and
future entry points (e.g., a Failed-tab "Open the partial .md" action).
Single test surface.

---

## Data model + queries

No schema changes. The Library page reads:

```sql
SELECT
    e.guid, e.show_slug, e.title, e.pub_date,
    e.duration_sec, e.completed_at
FROM episodes e
WHERE e.status = 'done'
ORDER BY e.pub_date DESC;
```

Then for each row, resolve the on-disk `.md` path via
`LibraryIndex.path_for(guid)` (the existing scanner). Rows with a
missing on-disk file get filtered out client-side.

For the show tree, a second tiny query:

```sql
SELECT show_slug, COUNT(*) AS n
FROM episodes
WHERE status = 'done'
GROUP BY show_slug
ORDER BY show_slug;
```

Joined against `ctx.watchlist.shows` for `title` + `source` per show.

Refresh strategy:

- Build once on Library page show.
- Re-build on `episode_done` signal (one new row, rebuild the affected
  show node + insert the row at the top of the list).
- Re-build on `LibraryIndex` filesystem-watcher events (e.g., user
  drops a transcript into the output dir manually).

---

## Files

- New `ui/library_tab.py` — the `LibraryTab(QWidget)` class.
- New `core/macopen.py` — the `open_with_chooser` + `open_default` +
  `reveal_in_finder` helpers.
- Modify `ui/main_window.py` — sidebar rename + new "Library" entry +
  stack widget for the LibraryTab.
- Modify `ui/widgets/sidebar.py` — only if a string-replace doesn't
  cover everything; group title is data-driven.
- Tests:
  - `tests/test_macopen.py` — unit tests with subprocess mocked.
  - `tests/test_library_tab.py` — bare-`QApplication` smoke that
    constructs the tab against a tmp state DB + tmp output_root.

---

## Out of scope

- In-app audio playback. The user opens the `.mp3` via "Reveal in
  Finder" → double-click in QuickTime/etc.
- Full-text search across transcripts (already tracked as v2.0 horizon
  item, depends on FTS5).
- Drag-and-drop episodes into other apps.
- Tagging / favouriting episodes.
- Export selected → ZIP / share sheet.

---

## Phasing

Ships as one commit (UI + helper) since the LibraryTab needs the
helper module to be useful, and the sidebar rename is one file edit.
If complexity grows, can split into:

1. `core/macopen.py` + tests.
2. Sidebar rename + LibraryTab skeleton (tree + list, no preview).
3. Preview pane.
