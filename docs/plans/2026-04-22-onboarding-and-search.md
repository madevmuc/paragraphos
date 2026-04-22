# Onboarding + Search Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship v1.1.9 — a guided setup dialog for transcripts folder + Obsidian, consolidated Obsidian settings, `~/Desktop` picker defaults, universal slug auto-fill, and a richer search-results table with lazy feed probing.

**Architecture:** Two new UI modules (`ui/setup_dialog.py`, `ui/widgets/show_results_table.py`) and one new worker module (`ui/feed_probe.py`). Settings gains a `setup_completed` flag with backfill for legacy users. A new pure helper `core.sanitize.slugify()` centralises slug generation. The rich search table uses a `QThreadPool` for lazy, viewport-aware feed probes.

**Tech Stack:** PyQt6 6.7, Python 3.12, existing `core.artwork` / `core.rss` / `core.discovery` / `core.settings` helpers. Tests use pytest + `QT_QPA_PLATFORM=offscreen`.

**Design doc:** `docs/plans/2026-04-22-onboarding-and-search-design.md`.

Working branch: `ship-v1` (continue linear history).

Related skills:
- @superpowers:test-driven-development
- @superpowers:requesting-code-review

---

## Task 1: `core.sanitize.slugify()`

**Files:** Modify `core/sanitize.py` (grep first — file exists, has related helpers; integrate alongside them). Create `tests/test_slugify.py`.

**Step 1 — failing tests** (`tests/test_slugify.py`):
```python
import pytest
from core.sanitize import slugify


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Tech! Podcast — Show", "tech-podcast-show"),
        ("  Multiple   Spaces ", "multiple-spaces"),
        ("Die Drei ???", "die-drei"),
        ("C'est la vie", "c-est-la-vie"),
        ("Emojis 🎙 dropped", "emojis-dropped"),
        ("", "show"),
        ("---", "show"),
        ("Über Café", "uber-cafe"),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected
```

**Step 2 — verify fail:** `cd /Users/matthiasmaier/dev/paragraphos && .venv/bin/python -m pytest tests/test_slugify.py -v` → ImportError.

**Step 3 — implement:**
```python
# core/sanitize.py (add alongside existing helpers)
import re
import unicodedata


def slugify(title: str) -> str:
    """Pure-kebab slug: NFKD-strip diacritics, lowercase, non-alphanum runs
    collapse to a single '-', trimmed. Returns 'show' on empty/collapsed."""
    normalised = unicodedata.normalize("NFKD", title or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    collapsed = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return collapsed or "show"
```

**Step 4:** pytest all passes + `.venv/bin/python -m pytest -q` all green.

**Step 5:** `git add core/sanitize.py tests/test_slugify.py && git commit -m "feat(sanitize): slugify() for kebab-case show slugs"`.

---

## Task 2: Settings — `setup_completed` flag + migration + new defaults

**Files:** `core/models.py`, `ui/app_context.py` (likely wraps settings load — check), `tests/test_settings_migration.py` (new).

**Step 1 — failing tests:**
```python
# tests/test_settings_migration.py
from core.models import Settings
from core.settings import backfill_setup_completed


def test_fresh_defaults_have_flag_false():
    s = Settings()
    assert s.setup_completed is False


def test_backfill_flips_flag_when_output_root_customised():
    s = Settings()
    s.output_root = "/Users/alice/Transcripts"
    backfill_setup_completed(s)
    assert s.setup_completed is True


def test_backfill_leaves_flag_false_on_pure_defaults():
    s = Settings()
    backfill_setup_completed(s)
    assert s.setup_completed is False


def test_backfill_respects_existing_true():
    s = Settings()
    s.setup_completed = True
    backfill_setup_completed(s)
    assert s.setup_completed is True
```

**Step 2 — verify fail.**

**Step 3 — implement:**
- `core/models.py`: add `setup_completed: bool = False`. Change defaults:
  ```python
  output_root: str = "~/Desktop/Paragraphos/transcripts"
  obsidian_vault_path: str = ""
  knowledge_hub_root: str = ""
  ```
  (Existing users keep their saved values via yaml load; only new installs see these.)
- `core/settings.py` (or wherever Settings is loaded — grep first, but `backfill_setup_completed` goes there): add helper:
  ```python
  def backfill_setup_completed(s: Settings) -> None:
      if s.setup_completed:
          return
      defaults = Settings()
      if (
          s.output_root != defaults.output_root
          or s.obsidian_vault_path != defaults.obsidian_vault_path
          or s.knowledge_hub_root != defaults.knowledge_hub_root
      ):
          s.setup_completed = True
  ```
  Call it from the settings loader after yaml parse.

**Step 4:** full suite green.

**Step 5:** commit `feat(settings): setup_completed flag + migration + sane new-install defaults`.

---

## Task 3: Folder-picker default → `~/Desktop`

**Files:** `ui/settings_pane.py` (4 `_pick_*` methods), `tests/test_settings_pane_pickers.py` (new).

**Step 1 — failing tests:**
```python
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from ui.settings_pane import SettingsPane  # adjust import if dep-injection needed


def test_pick_output_root_starts_at_desktop_when_field_empty(tmp_path, monkeypatch):
    _ = QApplication.instance() or QApplication([])
    # Build a minimal fake ctx with an empty output_root.
    from core.models import Settings
    class FakeCtx:
        settings = Settings()
        data_dir = tmp_path
    pane = SettingsPane(FakeCtx())
    pane.output.setText("")
    captured = {}

    def fake_dlg(parent, title, directory):
        captured["dir"] = directory
        return ""
    with patch("ui.settings_pane.QFileDialog.getExistingDirectory", fake_dlg):
        pane._pick_output_root()
    assert captured["dir"] == str(Path.home() / "Desktop")
```

**Step 2 — verify fail.**

**Step 3 — implement:** extract helper in `ui/settings_pane.py`:
```python
def _default_picker_dir(self, current: str) -> str:
    p = Path(current).expanduser() if current else Path()
    if current and p.exists():
        return str(p)
    return str(Path.home() / "Desktop")
```
Refactor the 4 `_pick_*` methods to use it: `start = self._default_picker_dir(self.output.text())` etc.

**Step 4:** tests green.

**Step 5:** commit `fix(settings): folder pickers default to ~/Desktop when path is empty or missing`.

---

## Task 4: Apply `slugify` in `add_show_dialog`

**Files:** `ui/add_show_dialog.py`. Extend `tests/test_first_run_wizard.py`? No — a new `tests/test_add_show_slug.py` (new).

**Step 1 — tests:**
```python
# tests/test_add_show_slug.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from core.sanitize import slugify


def test_name_path_uses_slugify(tmp_path, monkeypatch):
    from ui.app_context import AppContext
    from ui.add_show_dialog import AddShowDialog

    _ = QApplication.instance() or QApplication([])
    ctx = AppContext.load(tmp_path)
    dlg = AddShowDialog(ctx, None)
    # Simulate _pick_name_result-style fill.
    meta = {"title": "Die Drei ???!", "author": "Europa"}
    dlg._loaded_meta = meta
    dlg.name_title.setText(meta["title"])
    dlg.name_slug.setText(slugify(meta["title"]))
    assert dlg.name_slug.text() == "die-drei"


def test_apple_path_sets_slug_via_slugify(tmp_path):
    from ui.app_context import AppContext
    from ui.add_show_dialog import AddShowDialog

    _ = QApplication.instance() or QApplication([])
    ctx = AppContext.load(tmp_path)
    dlg = AddShowDialog(ctx, None)
    dlg._loaded_meta = {"title": "Darknet Diaries", "author": "Jack"}
    dlg._loaded_manifest = []
    dlg._loaded_rss = "https://example.com/rss"
    # Spy on _do_save to capture the slug.
    captured = {}
    dlg._do_save = lambda show: captured.update(show)  # type: ignore[method-assign]
    dlg._add_from_apple()
    assert captured["slug"] == "darknet-diaries"
```

**Step 2 — verify fail** (current `_add_from_apple` sets `slug = title.lower().replace(" ", "-")`, same result for "Darknet Diaries", so this test might pass; adjust title to something `slugify` normalises differently, e.g. `"Darknet: Diaries — Jack"` → `"darknet-diaries-jack"`). Before committing the test, run it against HEAD to confirm it fails.

**Step 3 — implement:** in `ui/add_show_dialog.py`:
- Import `from core.sanitize import slugify`.
- Replace the three `title.lower().replace(" ", "-")` sites (name, url, apple) with `slugify(title)`.

**Step 4:** tests green.

**Step 5:** commit `feat(add-show): uniform slugify() in Name/URL/Apple paths`.

---

## Task 5: `ui/feed_probe.py` — FeedProbeWorker

**Files:** `ui/feed_probe.py` (new), `tests/test_feed_probe.py` (new).

**Step 1 — failing tests:**
```python
# tests/test_feed_probe.py
import os
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QCoreApplication

from ui.feed_probe import FeedProbeWorker


def test_probe_emits_success(tmp_path):
    app = QCoreApplication.instance() or QCoreApplication([])
    manifest = [
        {"guid": "a", "title": "Old", "pubDate": "2024-01-01T00:00:00"},
        {"guid": "b", "title": "Mid", "pubDate": "2024-06-01T00:00:00"},
        {"guid": "c", "title": "New", "pubDate": "2024-12-01T00:00:00"},
    ]
    received = {}
    def fake_fetch(url, timeout=10.0):
        return ("canonical", manifest, None, None)
    worker = FeedProbeWorker(row_index=3, feed_url="https://e/r")
    worker.done.connect(lambda r: received.update({"row": r[0], "n": r[1], "date": r[2], "title": r[3]}))
    with patch("ui.feed_probe.fetch_feed", fake_fetch):
        worker.run()
    deadline = time.time() + 2
    while "row" not in received and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    assert received == {"row": 3, "n": 3, "date": "2024-12-01T00:00:00", "title": "New"}


def test_probe_emits_failure_tuple():
    app = QCoreApplication.instance() or QCoreApplication([])
    received = {}
    worker = FeedProbeWorker(row_index=7, feed_url="https://broken")
    worker.done.connect(lambda r: received.update({"row": r[0], "n": r[1]}))
    def boom(url, timeout=10.0):
        raise RuntimeError("network")
    with patch("ui.feed_probe.fetch_feed", boom):
        worker.run()
    app.processEvents()
    assert received == {"row": 7, "n": None}
```

**Step 2 — verify fail.**

**Step 3 — implement:**
```python
# ui/feed_probe.py
from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from core.rss import fetch_feed


class _Signals(QObject):
    done = pyqtSignal(tuple)  # (row_index, ep_count, latest_date, latest_title) — n=None on fail


class FeedProbeWorker(QRunnable):
    """Lightweight feed-probe for the search-results table. Runs on a
    shared QThreadPool; emits a single `done` tuple on completion."""

    def __init__(self, row_index: int, feed_url: str):
        super().__init__()
        self._row = row_index
        self._url = feed_url
        self._signals = _Signals()
        self.done = self._signals.done

    def run(self) -> None:
        try:
            _, manifest, _, _ = fetch_feed(self._url, timeout=8.0)
            if not manifest:
                self._signals.done.emit((self._row, 0, None, None))
                return
            latest = manifest[-1]
            self._signals.done.emit((self._row, len(manifest), latest["pubDate"], latest["title"]))
        except Exception:
            self._signals.done.emit((self._row, None, None, None))
```

**Step 4:** tests green.

**Step 5:** commit `feat(feed-probe): QRunnable worker fetches feed ep-count + newest`.

---

## Task 6: `ui/widgets/show_results_table.py` — ShowResultsTable

**Files:** `ui/widgets/show_results_table.py` (new), `tests/test_show_results_table.py` (new).

**Step 1 — failing tests:**
```python
# tests/test_show_results_table.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from core.discovery import PodcastMatch
from ui.widgets.show_results_table import ShowResultsTable


def _match(title="Show", author="Author", feed="https://e/r", art=None, coll_id=42):
    return PodcastMatch(title=title, author=author, feed_url=feed,
                        artwork_url=art, itunes_collection_id=coll_id)


def test_set_matches_renders_placeholders():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A"), _match(title="B")])
    assert tbl.rowCount() == 2
    # Columns: 0=cover 1=title 2=author 3=eps 4=latest 5=newest-title
    assert tbl.item(0, 1).text() == "A"
    assert tbl.item(0, 3).text() == "…"
    assert tbl.item(0, 5).text() == "…"


def test_apply_probe_result_fills_cells():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A")])
    tbl.apply_probe_result((0, 12, "2024-12-01T00:00:00", "Newest Ep"))
    assert tbl.item(0, 3).text() == "12"
    assert "2024-12-01" in tbl.item(0, 4).text()
    assert tbl.item(0, 5).text() == "Newest Ep"


def test_apply_probe_failure_shows_emdash():
    _ = QApplication.instance() or QApplication([])
    tbl = ShowResultsTable()
    tbl.set_matches([_match(title="A")])
    tbl.apply_probe_result((0, None, None, None))
    assert tbl.item(0, 3).text() == "—"
    assert tbl.item(0, 4).text() == "—"
    assert tbl.item(0, 5).text() == "—"
```

**Step 2 — verify fail.**

**Step 3 — implement:** (~80 LOC) QTableWidget subclass. Column setup, `set_matches(matches)`, `apply_probe_result(tuple)`, plus `feed_url_for_row(row)` helper used by the parent dialog on select. Cover loading is stubbed in this task — left as a placeholder icon; Task 7 wires it.

**Step 4:** tests green.

**Step 5:** commit `feat(widgets): ShowResultsTable — cover/title/author/episodes/latest/newest`.

---

## Task 7: Wire ShowResultsTable into Name mode

**Files:** `ui/add_show_dialog.py`. Extend `tests/test_add_show_slug.py` or new `tests/test_add_show_table_wiring.py`.

Delta:
- Replace `self.results = QListWidget()` with `self.results = ShowResultsTable()`.
- Replace `results.itemDoubleClicked` with `results.cellDoubleClicked` → call `_pick_name_result` adapted to take `(row, col)` and read the match via `self.results.feed_url_for_row(row)`.
- `_render_name_results(matches)` → `self.results.set_matches(matches); self._probe_visible_rows()`.
- New `_probe_visible_rows()`: first run enqueues row 0–9 via a shared `QThreadPool`; subsequent calls compute viewport via `rowAt(0)` + `rowAt(self.results.viewport().height())` and probe any newly-visible rows not already probed.
- Track `self._probed_rows: set[int]` to avoid re-probing.
- Cover loading: spawn a lightweight `QThreadPool` worker per row (reuse `core.artwork.fetch_cached` if it exists; otherwise just write a minimal `ui.cover_loader.CoverWorker(QRunnable)` that fetches and emits `QPixmap`).

**Step 4:** tests green.

**Step 5:** commit `feat(add-show): Name mode uses ShowResultsTable with hybrid probe`.

---

## Task 8: `ui/setup_dialog.py` — 3-page guided setup

**Files:** `ui/setup_dialog.py` (new), `tests/test_setup_dialog.py` (new).

**Step 1 — failing tests:**
```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PyQt6.QtWidgets import QApplication

from core.models import Settings
from ui.setup_dialog import SetupDialog, show_setup_if_needed


def test_show_setup_returns_immediately_when_completed():
    _ = QApplication.instance() or QApplication([])
    s = Settings(setup_completed=True)
    # Should not raise / attempt to show the dialog.
    assert show_setup_if_needed(s) is True


def test_dialog_writes_output_root_on_finish_no_obsidian(tmp_path):
    _ = QApplication.instance() or QApplication([])
    s = Settings(setup_completed=False)
    dlg = SetupDialog(s)
    dlg._output_edit.setText(str(tmp_path))
    dlg._no_obsidian_btn.setChecked(True)
    dlg._finish()
    assert s.setup_completed is True
    assert s.output_root == str(tmp_path)
    assert s.obsidian_vault_path == ""


def test_dialog_writes_obsidian_path(tmp_path):
    _ = QApplication.instance() or QApplication([])
    s = Settings(setup_completed=False)
    vault = tmp_path / "MyVault"
    (vault / ".obsidian").mkdir(parents=True)
    dlg = SetupDialog(s)
    dlg._yes_obsidian_btn.setChecked(True)
    dlg._vault_edit.setText(str(vault))
    dlg._vault_colocate.setChecked(True)
    dlg._finish()
    assert s.setup_completed is True
    assert s.obsidian_vault_path == str(vault)
    assert s.obsidian_vault_name == "MyVault"
    assert s.output_root == str(vault / "raw" / "transcripts")
```

**Step 2 — verify fail.**

**Step 3 — implement:** QDialog + QStackedWidget with the three pages per the design doc. Reuse `~/Desktop` helper. `show_setup_if_needed(settings) -> bool` returns True if user dismissed via Finish (or skipped because flag already true).

**Step 4:** tests green.

**Step 5:** commit `feat(setup): 3-page guided setup dialog — folder + Obsidian`.

---

## Task 9: Show setup dialog after wizard

**Files:** `app.py`.

Hook after `FirstRunWizard` accepts. Also call `backfill_setup_completed` once at load.

```python
# app.py
from ui.setup_dialog import show_setup_if_needed
from core.settings import backfill_setup_completed

# after FirstRunWizard path succeeds / is skipped:
backfill_setup_completed(ctx.settings)
if not show_setup_if_needed(ctx.settings):
    sys.exit(0)
ctx.save_settings()
```

(Adjust to whatever helper the existing `ctx.settings` uses to persist.)

Commit: `feat(onboarding): show setup dialog after wizard on fresh install`.

---

## Task 10: Settings pane — consolidate Obsidian into a group box

**Files:** `ui/settings_pane.py`.

Wrap `obsidian_vault_path` + `obsidian_vault_name` + `_pick_obsidian` into a `QGroupBox("Obsidian")`. Preview line under them: *"Transcripts will be written to `<output_root>`"* (live-updated when either field changes — hook both `textChanged` signals). If the other tab(s) currently render these fields, remove them from there.

No new tests (this is pure layout reshuffle). Verify with full suite green.

Commit: `refactor(settings): Obsidian fields in their own group box`.

---

## Task 11: Help → Re-run setup guide menu entry

**Files:** `ui/menu_bar.py`.

Add entry under Help:
```python
action_rerun = QAction("Re-run setup guide…", window)
action_rerun.triggered.connect(lambda: _rerun_setup(window))
help_menu.addAction(action_rerun)

def _rerun_setup(window) -> None:
    window.ctx.settings.setup_completed = False  # force show
    from ui.setup_dialog import SetupDialog
    SetupDialog(window.ctx.settings, window).exec()
    window.ctx.save_settings()
```

Commit: `feat(menu): Help → Re-run setup guide entry`.

---

## Task 12: Hide wiki-compile banner when Obsidian isn't configured

**Files:** `ui/main_window.py`, `tests/test_main_window_banner.py` (new).

**Context:** `_refresh_banner` currently shows a banner whenever transcripts are newer than the last wiki compile — but the whole concept of a "wiki compile" only makes sense if the user is running an Obsidian / knowledge-hub workflow. Users on plain folders should never see it.

**Step 1 — failing test:**
```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from PyQt6.QtWidgets import QApplication


def test_compile_banner_hidden_when_no_obsidian(tmp_path, monkeypatch):
    _ = QApplication.instance() or QApplication([])
    from ui.main_window import MainWindow
    # Force a settings state that would normally trigger the banner:
    # transcripts newer than last_compiled. But obsidian_vault_path is
    # empty → banner must stay hidden.
    w = MainWindow()
    w.ctx.settings.obsidian_vault_path = ""
    # Ensure there's a pretend output_root with fresh files.
    output = tmp_path / "out"
    output.mkdir()
    (output / "ep.md").write_text("fresh")
    w.ctx.settings.output_root = str(output)
    w._refresh_banner()
    assert not w.banner.isVisible() or w._banner_state != "compile"
```

**Step 2 — verify fail.**

**Step 3 — implement:** in `_refresh_banner`, add an early short-circuit:
```python
if not (getattr(self.ctx.settings, "obsidian_vault_path", "") or ""):
    if self._banner_state == "compile":
        self._banner_state = ""
        self.banner.setVisible(False)
    return
```
Place it after the update-banner check (update banner wins over everything, including this check), before the `output_root` / `last_compiled` logic.

**Step 4:** tests green.

**Step 5:** commit `fix(banner): hide wiki-compile banner unless Obsidian is configured`.

---

## Task 13: Version bump + CHANGELOG + release prep

**Files:** `core/version.py`, `pyproject.toml`, `CHANGELOG.md`.

Bump to `1.1.9`. CHANGELOG entry:

```markdown
## v1.1.9 — 2026-04-22 (onboarding + search polish)

### Added
- **Setup guide.** After the first-run wizard, a 3-page dialog asks where
  transcripts should go (default `~/Desktop/Paragraphos/transcripts`) and
  whether you use Obsidian. Picks up `.obsidian/`-marked vaults and can
  co-locate transcripts inside them. Re-runnable via Help → Re-run setup guide.
- **Rich search-results table.** Name-mode results now show cover, title,
  author, episode count, newest episode date + title. Feed probes run
  lazily in the background, viewport-aware.
- **Scroll-triggered auto-load.** Reaching the bottom of the result list
  auto-fetches the next 50, up to iTunes' 200-item cap.

### Changed
- Folder pickers default to `~/Desktop` when the current field is empty.
- Obsidian settings consolidated into a dedicated group box.
- New-install defaults no longer point at author-specific paths.
- Slug auto-fill now uses proper Unicode-aware slugify on every add path.

### Fixed
- Apple Podcasts add path now sets a slug (previously empty).
- Wiki-compile banner no longer shows for users who aren't using
  Obsidian (it made no sense outside an Obsidian workflow).
```

Run full suite. Commit: `chore(release): v1.1.9 — onboarding & search polish`.

---

## Notes for the executor

- Each task = its own commit. Pre-commit hook runs ruff + ruff-format + pytest. If hooks fail, fix and commit again (don't --amend).
- Keep tests deterministic — no real network calls (mock `fetch_feed`, `search_itunes`).
- `QT_QPA_PLATFORM=offscreen` is required for Qt tests.
- Don't push, tag, or bump `main` — controller handles release flow after all 12 tasks are green.
