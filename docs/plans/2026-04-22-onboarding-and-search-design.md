# Onboarding + search polish — design

**Date:** 2026-04-22
**Status:** approved, ready for implementation planning
**Ship as:** v1.1.9

## Problem

Two threads of UX feedback:

1. **Onboarding cliff.** The v1.1.8 first-run wizard gets deps installed, then drops the user into the main window without asking where transcripts should go or whether they use Obsidian. Defaults point at the author's development paths (`~/dev/knowledge-hub/...`) which are wrong for every other user. Settings fields for Obsidian are scattered across tabs.
2. **Search-result poverty.** The name-search list is a plain `QListWidget` showing `"<title> — <author>"`. Users report they can't tell matching shows apart, and the result set was capped at 10 until yesterday's fixes. Even the new 50-item list plus auto-load doesn't give users the "# of episodes", "newest episode date", or cover art they actually use to pick.

## Goals

- New users set their transcripts folder and Obsidian preference before the main window opens.
- Obsidian-related settings all live in one place.
- Folder pickers default to `~/Desktop` instead of the empty string / last value.
- Add-show slug auto-fills on every path (Name, URL, Apple).
- Name-mode search results surface cover, episode count, and newest-episode info — fetched lazily so the table renders instantly.

## Non-goals

- Multi-vault support.
- Per-show output-folder overrides.
- Importing anything beyond "this folder is an Obsidian vault" (user picked option A).
- Reworking the URL or Apple modes' inputs.

## Design

### Part 1 — Setup dialog

New `ui/setup_dialog.py`. Shown by `app.py` after `FirstRunWizard.accept()` returns, gated by a new `settings.setup_completed: bool` flag. If the flag is True, dialog is skipped.

Three pages inside a `QStackedWidget`:

- **Page 1 — Transcripts folder.** `QLineEdit` prefilled with `~/Desktop/Paragraphos/transcripts`, adjacent `"Choose folder…"` button opens `QFileDialog.getExistingDirectory(..., dir=str(Path.home() / "Desktop"))`. Live preview under the field: *"Files will be written as `<path>/<show-slug>/<episode>.md`"*.
- **Page 2 — Obsidian?** Two large radio buttons: *"Yes, I use Obsidian"* / *"No, plain folders"*. No → skip to Finish. Yes → Page 3.
- **Page 3 — Pick vault.** Picker starts at `~/Documents` if it contains any child dir that has a `.obsidian/` subdir, else `~/Desktop`. When user picks a folder, if it contains `.obsidian/`, the dialog confirms *"Detected Obsidian vault: `<folder-name>`"* and auto-fills `obsidian_vault_name = Path(d).name`. Checkbox (default on): *"Put transcripts inside the vault at `<vault>/raw/transcripts`"*; when ticked, Page 1's `output_root` is overridden with that path.

Finish button on Page 1 (when No-Obsidian path is taken via Page 2) and on Page 3 (Yes path). Sets `setup_completed = True` + saves Settings + closes.

Re-runnable via **Help → Re-run setup guide** (menu entry added to `ui/menu_bar.py`).

**Migration for existing users.** On first load after upgrading to v1.1.9, if `settings.output_root`, `obsidian_vault_path`, or `knowledge_hub_root` differs from the default in `core/models.py`, mark `setup_completed = True` automatically so the dialog doesn't ambush them.

### Part 2 — Settings pane consolidation

`ui/settings_pane.py` grows an explicit **"Obsidian"** `QGroupBox`:

```
Obsidian
├── Vault path  [ /Users/.../vault   ] [ Pick… ]
├── Vault name  [ auto from basename  ]
└── Preview: Transcripts will be written to <path> (opens in Obsidian via your vault)
```

Fields `obsidian_vault_path` and `obsidian_vault_name` are moved into this group box; wherever they were before is removed. The other three folder pickers (`_pick_output_root`, `_pick_knowledge_hub_root`, `_pick_obsidian`, `_pick_export_root`) gain the same `~/Desktop` fallback logic as the setup dialog: if the current field is empty or points at a non-existent path, start the picker at `~/Desktop`.

### Part 3 — Slug auto-fill everywhere

Extract `core.slugify(title: str) -> str` in `core/sanitize.py` (module already exists for related helpers):
- Unicode NFKD normalise; drop combining marks.
- Lowercase.
- Replace non-`[a-z0-9]` runs with single `-`.
- Trim leading/trailing `-`.
- Return `"show"` if input collapses to empty.

Apply in `ui/add_show_dialog.py`:
- `_pick_name_result` / `_fill_from_feed_sync`: currently uses `.lower().replace(" ", "-")` — swap to `slugify(title)`.
- `_add_from_url`: same.
- `_add_from_apple`: currently doesn't set slug at all — add `slug = slugify(meta.get("title") or "")` and populate. If user wants to customise, they go through "Customise…" which switches to Name mode where the slug field is editable.

### Part 4 — Rich search-results table (Hybrid C)

Replace the Name-mode `QListWidget` with a `QTableWidget` subclass `ShowResultsTable` (new, `ui/widgets/show_results_table.py`). Columns:

| Cover | Title | Author | Episodes | Latest | Newest episode |
|---|---|---|---|---|---|
| 48 px icon | bold | ink_3 | right-aligned number | ISO date | ellipsed on resize |

Row height fixed at 52 px so cover artwork fits. Columns 3–5 auto-fit; col 4 stretches.

**Data flow:**
1. On `_search_by_name`, render rows immediately from `search_itunes(term)` with cover + title + author (plus `…` placeholders in the three feed-derived cells).
2. Covers download lazily via existing `core.artwork.fetch_cached(artwork_url, size=48)` — each into a `QThread` pool of size 4, cell refreshed on completion.
3. Feed probes use a new `ui.feed_probe.FeedProbeWorker(QObject)` — not a `QThread` subclass but a `QRunnable`-style object dispatched to a `QThreadPool` with max 6 concurrent threads. Emits `(row_index, ep_count, latest_date, latest_title)`. Failures emit `(row_index, None, None, None)` → cells render `"—"`.
4. Initial enqueue: first 10 rows on search.
5. Scroll: `verticalScrollBar().valueChanged` → compute which rows are now in the viewport via `rowAt(y)` for the scroll top and bottom; enqueue any not-yet-probed rows in that range.

The "Load 50 more" feature from `f36fc0a` (auto-load on scroll-to-bottom) is preserved in the table form. `_name_hint` label stays with the same messages.

### Part 5 — Settings / model changes

Add to `core/models.Settings`:
```python
setup_completed: bool = False
```
Migration runs on first `AppContext.load`:
```python
def _backfill_setup_completed(s: Settings) -> None:
    if s.setup_completed:
        return
    defaults = Settings()
    if (s.output_root != defaults.output_root
        or s.obsidian_vault_path != defaults.obsidian_vault_path
        or s.knowledge_hub_root != defaults.knowledge_hub_root):
        s.setup_completed = True
```

Also change **new-install defaults** in `core/models.py`:
```python
output_root: str = "~/Desktop/Paragraphos/transcripts"
obsidian_vault_path: str = ""  # empty = no Obsidian configured
knowledge_hub_root: str = ""
```

(The old `~/dev/knowledge-hub/...` defaults only ever worked for the author's machine. Existing users keep their saved values; only new installs see the new defaults.)

## Testing

- `test_slugify` — parametrised over `"Tech! Podcast — Show"` → `"tech-podcast-show"`, `"  Multiple   Spaces "` → `"multiple-spaces"`, `""` → `"show"`, diacritics, emoji drops.
- `test_setup_dialog_gated_on_flag` — flag True → `show_setup_if_needed()` returns without showing.
- `test_setup_dialog_writes_output_root_and_obsidian` — simulate Yes + vault + checkbox → assert settings persisted.
- `test_picker_default_is_desktop_when_path_missing` — mock `QFileDialog.getExistingDirectory`, assert `dir` kwarg equals `str(Path.home() / "Desktop")`.
- `test_backfill_setup_completed` — legacy settings with non-default output_root get `setup_completed=True` on load.
- `test_feed_probe_emits_signal_on_success` — stubbed feed returns 3 entries → signal emits `(row, 3, latest_iso, latest_title)`.
- `test_feed_probe_emits_failure_signal` — stubbed feed raises → signal emits `(row, None, None, None)`.
- `test_show_results_table_renders_placeholders_before_probe` — fresh table with 5 matches → cells 3-5 contain `"…"`.
- `test_show_results_table_updates_cell_on_probe_signal` — send probe signal for row 2 → cells 3-5 populated.

## Out of scope

- Importing Obsidian's `app.json` settings (user picked A).
- Multi-vault / per-vault transcripts folders.
- Real-time feed diff badges ("N new since last time").
- Internationalisation of new UI copy (English only).

## Next step

Hand off to `superpowers:writing-plans` for the step-by-step implementation plan; execute via `superpowers:subagent-driven-development` as a ~10-task release bundle targeting v1.1.9.
