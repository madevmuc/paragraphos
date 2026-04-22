# Theme A — YouTube Ingestion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add YouTube channels as first-class shows alongside podcasts and support ad-hoc YouTube video transcription, using captions when available and whisper as fallback.

**Architecture:** YouTube channels reuse the existing RSS pipeline via YouTube's hidden per-channel RSS feed (`/feeds/videos.xml?channel_id=UC...`). Backfill beyond the RSS 15-item cap uses `yt-dlp --flat-playlist`. yt-dlp itself is lazy-installed to a user-writable location on first YouTube use and self-updates via `yt-dlp -U`. Captions-first transcript path converts uploader-provided VTT to SRT; absent or rejected, the existing whisper pipeline takes over. The `Show` model gains a `source` discriminator; YouTube items live in the same `raw/transcripts/<slug>/` folder as podcasts.

**Tech Stack:** Python 3.12, PyQt6 6.7, existing `core.rss` / `core.pipeline` / `core.transcriber` / `core.downloader`, yt-dlp (lazy-installed binary, not a build dep). Tests use pytest + `QT_QPA_PLATFORM=offscreen`.

**Design doc:** `docs/plans/2026-04-22-youtube-and-auto-update-design.md`.

**Working branch:** `ship-v1` (continue linear history; tag intermediate as v1.2.0 once Theme A lands).

**Related skills:**
- @superpowers:test-driven-development
- @superpowers:requesting-code-review
- @superpowers:verification-before-completion

---

## Task 1: `Show.source` discriminator + migration

**Files:**
- Modify: `core/models.py` (add field to `Show`).
- Modify: `core/models.py` (extend `backfill_setup_completed` or add a new backfill step in the same function).
- Test: `tests/test_models.py` (extend) + `tests/test_settings_migration.py` (extend with watchlist case).

**Step 1: Failing test for new field default.**

Append to `tests/test_models.py`:

```python
def test_show_source_defaults_to_podcast():
    from core.models import Show
    s = Show(slug="x", title="X", rss="https://x/feed.xml")
    assert s.source == "podcast"


def test_show_source_accepts_youtube():
    from core.models import Show
    s = Show(slug="x", title="X", rss="https://youtube.com/feeds/videos.xml?channel_id=UC...",
             source="youtube")
    assert s.source == "youtube"
```

**Step 2: Verify fail.**

Run: `cd ~/dev/paragraphos && .venv/bin/python -m pytest tests/test_models.py -k source -v`
Expected: FAIL — `Show` has no `source` attribute.

**Step 3: Implement.**

Edit `core/models.py`, in `class Show`:

```python
class Show(BaseModel):
    slug: str
    title: str
    rss: str
    whisper_prompt: str = ""
    enabled: bool = True
    output_override: Optional[str] = None
    language: str = "de"
    artwork_url: str = ""
    # Source discriminator: "podcast" (RSS feed) or "youtube" (channel
    # RSS at /feeds/videos.xml?channel_id=UC...). Defaults to "podcast"
    # for backward compat with existing watchlist.yaml files.
    source: str = "podcast"
```

**Step 4: Run targeted tests.**

Run: `.venv/bin/python -m pytest tests/test_models.py -k source -v`
Expected: PASS.

**Step 5: Run full test suite.**

Run: `.venv/bin/python -m pytest -q`
Expected: all green.

**Step 6: Commit.**

```bash
git add core/models.py tests/test_models.py
git commit -m "feat(models): Show.source discriminator (podcast|youtube)"
```

---

## Task 2: `core/sources.py` — Settings flag + helpers

Adds the `sources_podcasts` / `sources_youtube` settings (≥1 required) and a tiny helper module other modules import from to gate YouTube code paths.

**Files:**
- Modify: `core/models.py` (`Settings` class).
- Create: `core/sources.py`.
- Test: `tests/test_sources.py` (new).
- Migration: extend `backfill_setup_completed` in `core/models.py` to add the two new keys with default `True`.

**Step 1: Failing tests.**

Create `tests/test_sources.py`:

```python
import pytest
from core.models import Settings
from core.sources import (
    youtube_enabled,
    podcasts_enabled,
    validate_sources,
    SourcesError,
)


def test_defaults_both_on():
    s = Settings()
    assert podcasts_enabled(s)
    assert youtube_enabled(s)


def test_youtube_off_when_unchecked():
    s = Settings(sources_youtube=False)
    assert not youtube_enabled(s)


def test_at_least_one_required():
    s = Settings(sources_podcasts=False, sources_youtube=False)
    with pytest.raises(SourcesError):
        validate_sources(s)


def test_validate_passes_when_one_checked():
    validate_sources(Settings(sources_podcasts=False, sources_youtube=True))
    validate_sources(Settings(sources_podcasts=True, sources_youtube=False))
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_sources.py -v`
Expected: FAIL — `core.sources` module not found.

**Step 3: Implement.**

Edit `core/models.py` — add to `Settings`:

```python
    # Source filter — at least one must be True. Validated in
    # core.sources.validate_sources(). Default both on for backward
    # compat (existing users keep podcast behaviour).
    sources_podcasts: bool = True
    sources_youtube: bool = True
```

Create `core/sources.py`:

```python
"""Source-filter helpers: which content types the user has enabled.

YouTube ingestion code paths must call `youtube_enabled(settings)` and
no-op when False, so a user who unchecks YouTube in Settings doesn't
trigger yt-dlp installs or see YouTube UI.
"""

from __future__ import annotations

from core.models import Settings


class SourcesError(ValueError):
    """At least one source (podcasts or youtube) must be enabled."""


def podcasts_enabled(s: Settings) -> bool:
    return bool(s.sources_podcasts)


def youtube_enabled(s: Settings) -> bool:
    return bool(s.sources_youtube)


def validate_sources(s: Settings) -> None:
    if not (s.sources_podcasts or s.sources_youtube):
        raise SourcesError(
            "At least one source must be enabled (Podcasts or YouTube)."
        )
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_sources.py -v && .venv/bin/python -m pytest -q`
Expected: all green.

**Step 5: Commit.**

```bash
git add core/models.py core/sources.py tests/test_sources.py
git commit -m "feat(sources): podcast/youtube source-filter settings + validator"
```

---

## Task 3: Settings UI — Sources section

**Files:**
- Modify: `ui/settings_pane.py`.
- Test: `tests/test_settings_pane_pickers.py` (extend) — assert the new section + the at-least-one-checked enforcement.

**Step 1: Failing test.**

Append to `tests/test_settings_pane_pickers.py`:

```python
def test_sources_section_present(qtbot, tmp_path):
    from ui.settings_pane import SettingsPane
    from core.models import Settings
    from ui.app_context import AppContext  # use the existing test fixture in conftest

    pane = SettingsPane(_ctx_with_settings(Settings()))  # see conftest helper
    qtbot.addWidget(pane)
    assert pane.findChild(type(pane), "sources_group") is not None or \
        any("Sources" in w.text() for w in pane.findChildren(QLabel))


def test_unchecking_both_sources_blocks_save(qtbot, tmp_path):
    from ui.settings_pane import SettingsPane
    from core.models import Settings

    s = Settings()
    pane = SettingsPane(_ctx_with_settings(s))
    qtbot.addWidget(pane)
    pane.podcasts_checkbox.setChecked(False)
    pane.youtube_checkbox.setChecked(False)
    pane._save()  # auto-save handler
    # Both should snap back to at least one true; podcasts wins as default.
    assert s.sources_podcasts is True or s.sources_youtube is True
```

(If `_ctx_with_settings` doesn't exist in `conftest.py`, add a small helper there that returns a stub `AppContext` with `settings`, `state`, and a tmp `paths`.)

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_settings_pane_pickers.py -k source -v`
Expected: FAIL — checkboxes don't exist.

**Step 3: Implement in `ui/settings_pane.py`.**

Find the existing field-add helper (`_add_field`). Add a new "Sources" group near the top of the settings layout:

```python
# in SettingsPane._build_ui or equivalent, after the output-folder row
sources_group = QGroupBox("Sources")
sources_group.setObjectName("sources_group")
sl = QVBoxLayout(sources_group)
self.podcasts_checkbox = QCheckBox("Podcasts")
self.podcasts_checkbox.setChecked(self.ctx.settings.sources_podcasts)
self.podcasts_checkbox.toggled.connect(self._on_sources_changed)
self.youtube_checkbox = QCheckBox("YouTube")
self.youtube_checkbox.setChecked(self.ctx.settings.sources_youtube)
self.youtube_checkbox.toggled.connect(self._on_sources_changed)
sl.addWidget(self.podcasts_checkbox)
sl.addWidget(self.youtube_checkbox)
self.layout().addWidget(sources_group)
```

```python
def _on_sources_changed(self) -> None:
    p = self.podcasts_checkbox.isChecked()
    y = self.youtube_checkbox.isChecked()
    if not (p or y):
        # Snap back: keep podcasts on as the safe default.
        self.podcasts_checkbox.blockSignals(True)
        self.podcasts_checkbox.setChecked(True)
        self.podcasts_checkbox.blockSignals(False)
        p = True
    self.ctx.settings.sources_podcasts = p
    self.ctx.settings.sources_youtube = y
    self._save()  # existing auto-save
```

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_settings_pane_pickers.py -v`
Expected: PASS. Then full suite:
Run: `.venv/bin/python -m pytest -q`
Expected: all green.

**Step 5: Commit.**

```bash
git add ui/settings_pane.py tests/test_settings_pane_pickers.py tests/conftest.py
git commit -m "feat(settings): Sources section with podcast/youtube checkboxes"
```

---

## Task 4: `core/ytdlp.py` — Lazy-install resolver

Resolves the path to the user-writable yt-dlp binary; downloads it on first call. Uses GitHub Releases for the static binary (no Python pip install, keeps it self-updatable via `yt-dlp -U`).

**Files:**
- Create: `core/ytdlp.py`.
- Create: `tests/test_ytdlp.py`.

**Step 1: Failing tests.**

Create `tests/test_ytdlp.py`:

```python
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.ytdlp import (
    ytdlp_path,
    is_installed,
    install,
    self_update,
    YtdlpError,
)


def test_ytdlp_path_is_under_app_support(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    p = ytdlp_path()
    assert p == tmp_path / "bin" / "yt-dlp"


def test_is_installed_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    assert not is_installed()


def test_is_installed_true_when_executable(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    p = tmp_path / "bin" / "yt-dlp"
    p.parent.mkdir(parents=True)
    p.write_text("#!/bin/sh\necho yt-dlp 2026.03.30\n")
    p.chmod(0o755)
    assert is_installed()


def test_install_downloads_and_chmods(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    fake_http = MagicMock()
    fake_http.stream.return_value.__enter__.return_value.iter_bytes.return_value = [b"#!/bin/sh\n"]
    fake_http.stream.return_value.__enter__.return_value.headers = {"content-length": "10"}
    with patch("core.ytdlp.get_client", return_value=fake_http):
        install(progress=lambda done, total: None)
    p = tmp_path / "bin" / "yt-dlp"
    assert p.exists()
    assert p.stat().st_mode & 0o111  # executable bit set


def test_self_update_invokes_yt_dlp_dash_U(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    p = tmp_path / "bin" / "yt-dlp"
    p.parent.mkdir(parents=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    p.chmod(0o755)
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        self_update()
        run.assert_called_once()
        assert run.call_args[0][0] == [str(p), "-U"]
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_ytdlp.py -v`
Expected: FAIL — module missing.

**Step 3: Implement.**

Create `core/ytdlp.py`:

```python
"""yt-dlp lazy-installer + self-update wrapper.

yt-dlp lives at ~/Library/Application Support/Paragraphos/bin/yt-dlp,
NOT inside the .app bundle, so `yt-dlp -U` can replace itself without
breaking the app signature.

Public API:
- ytdlp_path() -> Path
- is_installed() -> bool
- install(progress=cb) -> None         (downloads from GitHub releases)
- self_update() -> None                (runs `yt-dlp -U`)
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Callable, Optional

from core.http import get_client
from core.paths import app_support_dir

APP_SUPPORT: Path = app_support_dir()  # patched in tests
DOWNLOAD_URL = (
    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
)


class YtdlpError(RuntimeError):
    """yt-dlp install or update failed."""


def ytdlp_path() -> Path:
    return APP_SUPPORT / "bin" / "yt-dlp"


def is_installed() -> bool:
    p = ytdlp_path()
    return p.exists() and bool(p.stat().st_mode & stat.S_IXUSR)


def install(progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Download yt-dlp to the user-writable bin dir.

    `progress(done_bytes, total_bytes)` is called periodically so the
    UI can show a progress bar.
    """
    target = ytdlp_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    client = get_client()
    try:
        with client.stream("GET", DOWNLOAD_URL, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            done = 0
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        tmp.chmod(tmp.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        tmp.replace(target)
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        raise YtdlpError(f"yt-dlp download failed: {e}") from e


def self_update() -> None:
    """Run `yt-dlp -U` in place. Raises YtdlpError on non-zero exit."""
    if not is_installed():
        raise YtdlpError("yt-dlp not installed; call install() first")
    p = ytdlp_path()
    proc = subprocess.run([str(p), "-U"], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise YtdlpError(f"yt-dlp -U failed: {proc.stderr.strip()}")
```

> If `core.paths.app_support_dir` doesn't exist, grep for the existing helper used by `core/state.py` (probably named differently) and reuse it. Do NOT hardcode `~/Library/...` — there's already a helper somewhere.

**Step 4: Verify pass.**

Run: `.venv/bin/python -m pytest tests/test_ytdlp.py -v && .venv/bin/python -m pytest -q`
Expected: all green.

**Step 5: Commit.**

```bash
git add core/ytdlp.py tests/test_ytdlp.py
git commit -m "feat(ytdlp): lazy-installer + self-update wrapper"
```

---

## Task 5: `ui/ytdlp_install_dialog.py` — Progress popup

Non-blocking modal that runs `core.ytdlp.install()` (or `self_update()`) on a worker thread, streams progress into a QProgressBar, and emits `installed`/`failed` signals.

**Files:**
- Create: `ui/ytdlp_install_dialog.py`.
- Create: `tests/test_ytdlp_install_dialog.py`.

**Step 1: Failing test.**

Create `tests/test_ytdlp_install_dialog.py`:

```python
from unittest.mock import patch
from PyQt6.QtCore import QEventLoop


def test_install_dialog_runs_install_and_emits_done(qtbot, tmp_path, monkeypatch):
    from ui.ytdlp_install_dialog import YtdlpInstallDialog
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)

    def fake_install(progress=None):
        if progress:
            progress(50, 100)
            progress(100, 100)
        (tmp_path / "bin").mkdir(parents=True)
        (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")

    with patch("core.ytdlp.install", side_effect=fake_install):
        dlg = YtdlpInstallDialog(mode="install")
        qtbot.addWidget(dlg)
        with qtbot.waitSignal(dlg.finished_install, timeout=3000) as sig:
            dlg.start()
        assert sig.args == [True]  # success
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_ytdlp_install_dialog.py -v`
Expected: FAIL — module missing.

**Step 3: Implement.**

Create `ui/ytdlp_install_dialog.py`:

```python
"""Modal dialog that installs or self-updates yt-dlp on a worker thread."""

from __future__ import annotations

from typing import Literal

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)

from core import ytdlp


class _Worker(QObject):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(bool, str)  # success, message

    def __init__(self, mode: Literal["install", "update"]) -> None:
        super().__init__()
        self.mode = mode

    def run(self) -> None:
        try:
            if self.mode == "install":
                ytdlp.install(progress=lambda d, t: self.progress.emit(d, t))
            else:
                ytdlp.self_update()
            self.done.emit(True, "")
        except Exception as e:
            self.done.emit(False, str(e))


class YtdlpInstallDialog(QDialog):
    finished_install = pyqtSignal(bool)  # True on success

    def __init__(self, mode: Literal["install", "update"] = "install", parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            "Installing yt-dlp" if mode == "install" else "Updating yt-dlp"
        )
        self._mode = mode
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Downloading yt-dlp so Paragraphos can fetch YouTube videos…"
                if mode == "install"
                else "Updating yt-dlp to keep YouTube downloads working…"
            )
        )
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        layout.addWidget(self._bar)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def start(self) -> None:
        self._thread = QThread(self)
        self._worker = _Worker(self._mode)
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._bar.setValue(int(100 * done / total))

    def _on_done(self, success: bool, message: str) -> None:
        self._thread.quit()
        self._thread.wait()
        self.finished_install.emit(success)
        if success:
            self.accept()
        else:
            self._bar.setFormat(f"Failed: {message}")
            self._buttons.setStandardButtons(QDialogButtonBox.StandardButton.Close)
```

**Step 4: Verify pass + suite.**

Run: `.venv/bin/python -m pytest tests/test_ytdlp_install_dialog.py -v && .venv/bin/python -m pytest -q`

**Step 5: Commit.**

```bash
git add ui/ytdlp_install_dialog.py tests/test_ytdlp_install_dialog.py
git commit -m "feat(ui): yt-dlp install/update progress dialog"
```

---

## Task 6: `core/youtube.py` — URL parsing + canonical RSS URL

Parses the user-pasted strings ("youtube.com/@handle", "youtube.com/channel/UC...", "youtu.be/<id>", "youtube.com/watch?v=<id>") and produces canonical channel-RSS URLs and video IDs. URL parsing first (no network); channel-id resolution from a handle uses yt-dlp.

**Files:**
- Create: `core/youtube.py`.
- Create: `tests/test_youtube.py`.

**Step 1: Failing tests.**

Create `tests/test_youtube.py`:

```python
import pytest
from core.youtube import (
    parse_youtube_url,
    rss_url_for_channel_id,
    YoutubeUrl,
    YoutubeUrlError,
)


@pytest.mark.parametrize("url,expected_kind,expected_value", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
     "channel_id", "UCuAXFkgsw1L7xaCfnd5JJOw"),
    ("https://www.youtube.com/@MrBeast", "handle", "MrBeast"),
    ("https://youtube.com/@MrBeast/videos", "handle", "MrBeast"),
])
def test_parse_known_forms(url, expected_kind, expected_value):
    p = parse_youtube_url(url)
    assert p.kind == expected_kind
    assert p.value == expected_value


def test_parse_rejects_unknown():
    with pytest.raises(YoutubeUrlError):
        parse_youtube_url("https://example.com/x")


def test_rss_url_for_channel_id():
    assert rss_url_for_channel_id("UC123") == \
        "https://www.youtube.com/feeds/videos.xml?channel_id=UC123"
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_youtube.py -v`
Expected: FAIL.

**Step 3: Implement.**

Create `core/youtube.py`:

```python
"""YouTube URL parsing + canonical-RSS helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse, parse_qs


YoutubeKind = Literal["video", "channel_id", "handle"]


class YoutubeUrlError(ValueError):
    """URL is not a recognisable YouTube video/channel/handle URL."""


@dataclass(frozen=True)
class YoutubeUrl:
    kind: YoutubeKind
    value: str  # video id, channel id, or handle (without @)


_VIDEO_ID_RE = re.compile(r"^[\w-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")


def parse_youtube_url(url: str) -> YoutubeUrl:
    u = urlparse(url.strip())
    host = (u.netloc or "").lower().lstrip("www.")
    path = u.path or ""

    if host == "youtu.be":
        vid = path.lstrip("/").split("/", 1)[0]
        if _VIDEO_ID_RE.match(vid):
            return YoutubeUrl("video", vid)
        raise YoutubeUrlError(f"bad video id: {vid!r}")

    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if path.startswith("/watch"):
            qs = parse_qs(u.query)
            v = (qs.get("v") or [""])[0]
            if _VIDEO_ID_RE.match(v):
                return YoutubeUrl("video", v)
            raise YoutubeUrlError(f"bad video id in query: {v!r}")
        if path.startswith("/channel/"):
            cid = path.split("/", 2)[2].split("/", 1)[0]
            if _CHANNEL_ID_RE.match(cid):
                return YoutubeUrl("channel_id", cid)
            raise YoutubeUrlError(f"bad channel id: {cid!r}")
        if path.startswith("/@"):
            handle = path[2:].split("/", 1)[0]
            if handle:
                return YoutubeUrl("handle", handle)

    raise YoutubeUrlError(f"unrecognised YouTube URL: {url!r}")


def rss_url_for_channel_id(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
```

**Step 4: Verify + suite.**

Run: `.venv/bin/python -m pytest tests/test_youtube.py -v && .venv/bin/python -m pytest -q`

**Step 5: Commit.**

```bash
git add core/youtube.py tests/test_youtube.py
git commit -m "feat(youtube): URL parsing + canonical channel-RSS helper"
```

---

## Task 7: `core/youtube_meta.py` — yt-dlp metadata fetcher

Wraps yt-dlp invocations: resolve handle → channel id, fetch channel preview metadata (title / artwork / video count), enumerate channel videos via `--flat-playlist`. Subprocess-based, mockable in tests.

**Files:**
- Create: `core/youtube_meta.py`.
- Create: `tests/test_youtube_meta.py`.

**Step 1: Failing tests.**

```python
# tests/test_youtube_meta.py
import json
from unittest.mock import patch, MagicMock

from core.youtube_meta import (
    resolve_handle_to_channel_id,
    fetch_channel_preview,
    enumerate_channel_videos,
    YoutubeMetaError,
)


def test_resolve_handle_calls_ytdlp_with_correct_url(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    fake_proc = MagicMock(returncode=0,
                          stdout=json.dumps({"channel_id": "UCabc"}),
                          stderr="")
    with patch("subprocess.run", return_value=fake_proc) as run:
        cid = resolve_handle_to_channel_id("MrBeast")
        assert cid == "UCabc"
        args = run.call_args[0][0]
        assert "https://www.youtube.com/@MrBeast" in args


def test_enumerate_channel_videos_parses_flat_playlist(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    output = "\n".join([
        json.dumps({"id": "vid1", "title": "First",  "timestamp": 1700000000}),
        json.dumps({"id": "vid2", "title": "Second", "timestamp": 1700001000}),
    ])
    fake_proc = MagicMock(returncode=0, stdout=output, stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        vids = enumerate_channel_videos("UCabc")
        assert [v["id"] for v in vids] == ["vid1", "vid2"]
        assert vids[0]["title"] == "First"


def test_fetch_channel_preview_returns_dict(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    payload = {
        "channel_id": "UCabc",
        "channel": "Mr Beast",
        "playlist_count": 700,
        "thumbnails": [{"url": "https://yt3/.../mqdefault.jpg", "width": 320}],
    }
    fake_proc = MagicMock(returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        prev = fetch_channel_preview("UCabc")
        assert prev["title"] == "Mr Beast"
        assert prev["video_count"] == 700
        assert prev["artwork_url"].startswith("https://")
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_youtube_meta.py -v`

**Step 3: Implement.**

Create `core/youtube_meta.py`:

```python
"""yt-dlp metadata wrappers for channel preview + video enumeration."""

from __future__ import annotations

import json
import subprocess
from typing import Dict, List

from core import ytdlp


class YoutubeMetaError(RuntimeError):
    """yt-dlp returned an error or unparseable output."""


def _run_ytdlp(args: List[str], timeout: int = 60) -> str:
    if not ytdlp.is_installed():
        raise YoutubeMetaError("yt-dlp not installed")
    cmd = [str(ytdlp.ytdlp_path()), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise YoutubeMetaError(f"yt-dlp failed: {proc.stderr.strip() or 'unknown error'}")
    return proc.stdout


def resolve_handle_to_channel_id(handle: str) -> str:
    out = _run_ytdlp([
        "--skip-download",
        "--print", "%(channel_id)j",
        f"https://www.youtube.com/@{handle}",
    ])
    # `--print %(channel_id)j` outputs a JSON-quoted string per video.
    # We only need the first line.
    line = out.strip().splitlines()[0]
    parsed = json.loads(line) if line.startswith('"') else json.loads(out.strip())
    if isinstance(parsed, dict):
        return parsed.get("channel_id") or ""
    return parsed  # plain string


def fetch_channel_preview(channel_id: str) -> Dict[str, object]:
    """Return {title, video_count, artwork_url, channel_id}."""
    out = _run_ytdlp([
        "--skip-download",
        "--playlist-items", "0",   # metadata only, no videos
        "--dump-single-json",
        f"https://www.youtube.com/channel/{channel_id}",
    ])
    data = json.loads(out)
    thumbs = data.get("thumbnails") or []
    artwork = thumbs[-1]["url"] if thumbs else ""
    return {
        "channel_id": data.get("channel_id") or channel_id,
        "title": data.get("channel") or data.get("title") or "",
        "video_count": int(data.get("playlist_count") or 0),
        "artwork_url": artwork,
    }


def enumerate_channel_videos(channel_id: str, *, limit: int | None = None) -> List[Dict]:
    args = [
        "--flat-playlist",
        "--dump-json",
        f"https://www.youtube.com/channel/{channel_id}",
    ]
    if limit:
        args[1:1] = ["--playlist-end", str(limit)]
    out = _run_ytdlp(args, timeout=180)
    return [json.loads(line) for line in out.splitlines() if line.strip()]
```

**Step 4: Verify + suite.**

Run: `.venv/bin/python -m pytest tests/test_youtube_meta.py -v && .venv/bin/python -m pytest -q`

**Step 5: Commit.**

```bash
git add core/youtube_meta.py tests/test_youtube_meta.py
git commit -m "feat(youtube_meta): yt-dlp wrappers for channel preview + enumerate"
```

---

## Task 8: `core/youtube_captions.py` — Caption fetch + VTT→SRT conversion

**Files:**
- Create: `core/youtube_captions.py`.
- Create: `tests/test_youtube_captions.py`.
- Create: `tests/fixtures/youtube/sample.en.vtt` (real-shaped VTT, ~5 cues).

**Step 1: Failing tests.**

```python
# tests/test_youtube_captions.py
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.youtube_captions import (
    fetch_manual_captions,
    vtt_to_srt,
    NoCaptionsAvailable,
)

FIXTURE = Path(__file__).parent / "fixtures" / "youtube" / "sample.en.vtt"


def test_vtt_to_srt_converts_basic_cue():
    vtt = FIXTURE.read_text()
    srt = vtt_to_srt(vtt)
    assert "1\n" in srt
    assert " --> " in srt
    assert ",000" in srt or "," in srt  # SRT uses commas in timestamps


def test_fetch_manual_returns_path(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # Simulate yt-dlp dropping the .vtt next to the requested filename.
    written_vtt = out_dir / "video.en.vtt"
    written_vtt.write_text(FIXTURE.read_text())

    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        srt_path = fetch_manual_captions("dQw4w9WgXcQ", out_dir / "video", lang="en")
        assert srt_path.exists()
        assert srt_path.suffix == ".srt"


def test_fetch_manual_raises_when_no_captions(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    fake_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        try:
            fetch_manual_captions("vid", tmp_path / "video", lang="en")
        except NoCaptionsAvailable:
            return
        raise AssertionError("expected NoCaptionsAvailable")
```

Create `tests/fixtures/youtube/sample.en.vtt`:

```
WEBVTT

00:00:00.000 --> 00:00:02.500
Welcome to the show.

00:00:02.500 --> 00:00:05.000
Today we are talking about regulation.

00:00:05.000 --> 00:00:09.000
And how it affects small businesses.
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_youtube_captions.py -v`

**Step 3: Implement.**

Create `core/youtube_captions.py`:

```python
"""YouTube caption fetch (via yt-dlp) and WebVTT → SRT conversion.

Manual (uploader-provided) captions only by default; auto-captions are
opt-in via the `auto_ok` flag.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from core import ytdlp


class NoCaptionsAvailable(RuntimeError):
    """yt-dlp returned no caption file for the requested language/kind."""


_VTT_TS = re.compile(r"(\d{2}:\d{2}:\d{2})\.(\d{3})")


def vtt_to_srt(vtt: str) -> str:
    """Convert WebVTT text to SRT. Drops cue settings + WEBVTT header."""
    lines = vtt.splitlines()
    # Strip WEBVTT header block (everything before the first blank line).
    try:
        i = lines.index("")
        body = lines[i + 1 :]
    except ValueError:
        body = lines

    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in body:
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)

    out: list[str] = []
    n = 0
    for blk in blocks:
        # Find the timestamp line; skip optional cue identifiers above it.
        ts_idx = next(
            (i for i, ln in enumerate(blk) if "-->" in ln), None
        )
        if ts_idx is None:
            continue
        ts_line = blk[ts_idx]
        # Drop any cue settings after the timestamps (e.g. "align:start").
        ts_line = ts_line.split("  ")[0]
        ts_line = _VTT_TS.sub(r"\1,\2", ts_line)
        text_lines = blk[ts_idx + 1 :]
        if not text_lines:
            continue
        n += 1
        out.append(str(n))
        out.append(ts_line)
        out.extend(text_lines)
        out.append("")
    return "\n".join(out)


def fetch_manual_captions(
    video_id: str,
    out_basename: Path,
    *,
    lang: str = "en",
    auto_ok: bool = False,
) -> Path:
    """Download captions for `video_id`. Returns path to converted .srt.

    `out_basename` is e.g. `/tmp/xyz/video` (no extension); yt-dlp will
    write `<basename>.<lang>.vtt` next to it.
    """
    if not ytdlp.is_installed():
        raise NoCaptionsAvailable("yt-dlp not installed")
    sub_kind = "--write-subs"
    extra = ["--sub-langs", lang, "--skip-download", "--sub-format", "vtt"]
    if auto_ok:
        extra.insert(0, "--write-auto-subs")
    cmd = [
        str(ytdlp.ytdlp_path()),
        sub_kind,
        *extra,
        "-o", str(out_basename),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise NoCaptionsAvailable(proc.stderr.strip())

    vtt_path = out_basename.with_suffix(f".{lang}.vtt")
    if not vtt_path.exists():
        raise NoCaptionsAvailable(f"no caption file produced: {vtt_path}")
    srt_path = out_basename.with_suffix(".srt")
    srt_path.write_text(vtt_to_srt(vtt_path.read_text(encoding="utf-8")), encoding="utf-8")
    return srt_path
```

**Step 4: Verify + suite.**

Run: `.venv/bin/python -m pytest tests/test_youtube_captions.py -v && .venv/bin/python -m pytest -q`

**Step 5: Commit.**

```bash
git add core/youtube_captions.py tests/test_youtube_captions.py tests/fixtures/youtube/sample.en.vtt
git commit -m "feat(youtube): caption fetch + VTT→SRT conversion"
```

---

## Task 9: `core/youtube_audio.py` — Audio-only download for whisper-fallback

**Files:**
- Create: `core/youtube_audio.py`.
- Create: `tests/test_youtube_audio.py`.

**Step 1: Failing test.**

```python
# tests/test_youtube_audio.py
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.youtube_audio import download_audio


def test_download_audio_invokes_correct_ytdlp_args(tmp_path, monkeypatch):
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)

    target = tmp_path / "out" / "video.mp3"
    target.parent.mkdir()

    def fake_run(cmd, **kw):
        # Simulate yt-dlp writing the mp3.
        target.write_bytes(b"fake mp3")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run) as run:
        result = download_audio("dQw4w9WgXcQ", target)
        assert result == target
        cmd = run.call_args[0][0]
        assert "--extract-audio" in cmd
        assert "--audio-format" in cmd
        assert "mp3" in cmd
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_youtube_audio.py -v`

**Step 3: Implement.**

Create `core/youtube_audio.py`:

```python
"""Audio-only YouTube download via yt-dlp, mapping to the existing
podcast-MP3 pipeline so transcribe.py treats it identically."""

from __future__ import annotations

import subprocess
from pathlib import Path

from core import ytdlp


class YoutubeDownloadError(RuntimeError):
    pass


def download_audio(video_id: str, target_mp3: Path, *, timeout: int = 600) -> Path:
    if not ytdlp.is_installed():
        raise YoutubeDownloadError("yt-dlp not installed")
    target_mp3.parent.mkdir(parents=True, exist_ok=True)
    # yt-dlp wants an output template WITHOUT the extension when extracting.
    template = str(target_mp3.with_suffix(""))
    cmd = [
        str(ytdlp.ytdlp_path()),
        "-f", "bestaudio",
        "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", f"{template}.%(ext)s",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise YoutubeDownloadError(proc.stderr.strip() or "unknown")
    if not target_mp3.exists():
        raise YoutubeDownloadError(f"yt-dlp did not produce {target_mp3}")
    return target_mp3
```

**Step 4: Verify + suite.**

**Step 5: Commit.**

```bash
git add core/youtube_audio.py tests/test_youtube_audio.py
git commit -m "feat(youtube): audio-only download wrapper"
```

---

## Task 10: Pipeline integration — captions-first, whisper-fallback

Hook YouTube items into `core/pipeline.py` so a `Show.source == "youtube"` episode runs through caption-fetch → if found, write `.md` + `.srt` directly; if not, fall back to existing audio-download + whisper path.

**Files:**
- Modify: `core/pipeline.py`.
- Modify: `core/models.py` (add per-show `youtube_transcript_pref` field on `Show`: `"captions" | "whisper" | "auto-captions"`, default `"captions"`).
- Modify: `core/models.py` `Settings` — add `youtube_default_transcript_source` mirror used when show field is not explicitly set.
- Test: `tests/test_pipeline.py` (extend with two cases).

**Step 1: Failing tests.**

Append to `tests/test_pipeline.py`:

```python
def test_youtube_episode_uses_captions_when_available(monkeypatch, tmp_path):
    from core.pipeline import process_episode
    from core.models import Show, Episode  # adapt to actual signatures

    show = Show(slug="ch", title="Channel", rss="...", source="youtube")
    ep = _make_yt_episode(video_id="vid1", show=show)  # helper adapted to current pipeline

    called = {"captions": False, "audio": False, "whisper": False}
    def fake_captions(vid, basename, lang="en", auto_ok=False):
        called["captions"] = True
        srt = basename.with_suffix(".srt")
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHi\n")
        return srt
    def fake_audio(vid, target, **kw): called["audio"] = True
    def fake_transcribe(*a, **kw): called["whisper"] = True

    monkeypatch.setattr("core.youtube_captions.fetch_manual_captions", fake_captions)
    monkeypatch.setattr("core.youtube_audio.download_audio", fake_audio)
    monkeypatch.setattr("core.transcriber.transcribe", fake_transcribe)

    process_episode(ep, ...)
    assert called["captions"] and not called["whisper"]


def test_youtube_episode_falls_back_to_whisper_when_no_captions(monkeypatch, tmp_path):
    from core.pipeline import process_episode
    from core.youtube_captions import NoCaptionsAvailable

    def fake_captions(*a, **k): raise NoCaptionsAvailable("none")
    called = {"audio": False, "whisper": False}
    def fake_audio(vid, target, **kw):
        called["audio"] = True
        target.write_bytes(b"fake")
    def fake_transcribe(*a, **k): called["whisper"] = True

    monkeypatch.setattr("core.youtube_captions.fetch_manual_captions", fake_captions)
    monkeypatch.setattr("core.youtube_audio.download_audio", fake_audio)
    monkeypatch.setattr("core.transcriber.transcribe", fake_transcribe)

    process_episode(_make_yt_episode("vid2"), ...)
    assert called["audio"] and called["whisper"]
```

> Adapt `_make_yt_episode` to the actual pipeline signature — read `core/pipeline.py` first to see what `process_episode` expects (likely an `Episode` dataclass with `show`, `mp3_url`, etc.). For YouTube items, the equivalent of `mp3_url` is the `https://www.youtube.com/watch?v=<id>` URL stored in the same field, with `show.source == "youtube"` as the discriminator.

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -k youtube -v`

**Step 3: Implement.**

In `core/pipeline.py`, add a branch at the top of `process_episode` (or wherever the per-episode dispatch happens):

```python
from core import youtube_captions, youtube_audio, youtube
from core.youtube_captions import NoCaptionsAvailable

def process_episode(ep, ctx, ...):
    if ep.show.source == "youtube":
        return _process_youtube_episode(ep, ctx)
    # ... existing podcast path unchanged ...

def _process_youtube_episode(ep, ctx):
    parsed = youtube.parse_youtube_url(ep.mp3_url)  # we stash the watch URL there
    if parsed.kind != "video":
        raise ValueError(f"YouTube episode without video URL: {ep.mp3_url!r}")
    vid = parsed.value
    pref = (ep.show.youtube_transcript_pref
            or ctx.settings.youtube_default_transcript_source)

    work = ctx.paths.work_dir(ep.show.slug, ep.guid)
    work.mkdir(parents=True, exist_ok=True)
    basename = work / "video"

    srt = None
    if pref in ("captions", "auto-captions"):
        try:
            srt = youtube_captions.fetch_manual_captions(
                vid, basename, lang=ep.show.language or "en",
                auto_ok=(pref == "auto-captions"),
            )
        except NoCaptionsAvailable:
            srt = None

    if srt is None:  # whisper fallback or pref == "whisper"
        mp3 = work / "audio.mp3"
        youtube_audio.download_audio(vid, mp3)
        srt = transcriber.transcribe(mp3, ...)  # existing call

    # render .md from .srt + frontmatter; reuse the existing renderer.
    write_episode_artifacts(ep, srt_path=srt, transcript_source=...)
```

Add to `core/models.py`:

```python
class Show(BaseModel):
    # ... existing fields ...
    # Per-show YouTube transcript preference. Empty = inherit from Settings.
    youtube_transcript_pref: str = ""  # "" | "captions" | "whisper" | "auto-captions"


class Settings(BaseModel):
    # ... existing fields ...
    # YouTube default transcript source when a show has no override.
    youtube_default_transcript_source: str = "captions"  # | "whisper" | "auto-captions"
```

**Step 4: Verify pass + full suite.**

Run: `.venv/bin/python -m pytest tests/test_pipeline.py -k youtube -v && .venv/bin/python -m pytest -q`

**Step 5: Commit.**

```bash
git add core/pipeline.py core/models.py tests/test_pipeline.py
git commit -m "feat(pipeline): YouTube episodes — captions-first, whisper-fallback"
```

---

## Task 11: YouTube frontmatter renderer

Update the markdown writer so `source: youtube` items emit the YouTube-specific frontmatter fields.

**Files:**
- Modify: `core/export.py` (or wherever the `.md` frontmatter is rendered — grep for `output_root` / `frontmatter` / `def render`).
- Test: `tests/test_export.py` (extend or create).

**Step 1: Failing test.**

```python
def test_youtube_frontmatter_fields():
    from core.export import render_episode_markdown
    md = render_episode_markdown(
        show_slug="myshow", title="Episode 1", srt_text="1\n00:00:00,000 --> 00:00:01,000\nHi\n",
        source="youtube",
        youtube_id="dQw4w9WgXcQ",
        channel_id="UCabc",
        transcript_source="captions",
    )
    assert "source: youtube" in md
    assert "youtube_id: dQw4w9WgXcQ" in md
    assert "youtube_url: https://youtu.be/dQw4w9WgXcQ" in md
    assert "channel_id: UCabc" in md
    assert "transcript_source: captions" in md
    assert "[Watch on YouTube](https://youtu.be/dQw4w9WgXcQ)" in md
```

**Step 2: Verify fail.**

**Step 3: Implement.** Read the current renderer, add the new optional kwargs. Existing podcast call sites pass `source="podcast"` (or default).

**Step 4: Verify + suite.**

**Step 5: Commit.**

```bash
git add core/export.py tests/test_export.py
git commit -m "feat(export): YouTube frontmatter + Watch-on-YouTube link"
```

---

## Task 12: `ui/add_show_dialog.py` — 4th mode "YouTube URL"

Add a 4th tab/segment to the existing 3-mode segmented control. Paste-only. Channel URL → preview card + backfill segmented control. Video URL → confirm attaching to existing channel or creating one-off.

**Files:**
- Modify: `ui/add_show_dialog.py`.
- Test: `tests/test_add_show_dialog_youtube.py` (new).

**Step 1: Failing tests.**

```python
def test_youtube_mode_visible_when_setting_on(qtbot, monkeypatch):
    from ui.add_show_dialog import AddShowDialog
    from core.models import Settings
    ctx = _ctx_with_settings(Settings(sources_youtube=True))
    dlg = AddShowDialog(ctx)
    qtbot.addWidget(dlg)
    assert dlg._has_youtube_mode()


def test_youtube_mode_hidden_when_setting_off(qtbot, monkeypatch):
    from ui.add_show_dialog import AddShowDialog
    from core.models import Settings
    ctx = _ctx_with_settings(Settings(sources_youtube=False))
    dlg = AddShowDialog(ctx)
    qtbot.addWidget(dlg)
    assert not dlg._has_youtube_mode()


def test_paste_channel_url_triggers_preview_fetch(qtbot, monkeypatch):
    from ui.add_show_dialog import AddShowDialog
    from core.models import Settings
    called = {}
    def fake_preview(cid):
        called["cid"] = cid
        return {"channel_id": cid, "title": "Mr Beast", "video_count": 700,
                "artwork_url": ""}
    monkeypatch.setattr("core.youtube_meta.fetch_channel_preview", fake_preview)
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)

    dlg = AddShowDialog(_ctx_with_settings(Settings()))
    qtbot.addWidget(dlg)
    dlg._activate_youtube_mode()
    dlg.youtube_url_input.setText("https://www.youtube.com/channel/UCabc1234567890123456789")
    dlg.youtube_url_input.editingFinished.emit()
    qtbot.waitUntil(lambda: "cid" in called, timeout=2000)
    assert called["cid"] == "UCabc1234567890123456789"
```

**Step 2: Verify fail.**

Run: `.venv/bin/python -m pytest tests/test_add_show_dialog_youtube.py -v`

**Step 3: Implement.**

Add a 4th segment to the existing segmented control in `AddShowDialog`. Skip rendering the segment when `not youtube_enabled(ctx.settings)`. The mode contains:

- `QLineEdit` `youtube_url_input` (placeholder: "Paste YouTube channel or video URL").
- After `editingFinished`, parse with `core.youtube.parse_youtube_url`. Branch:
  - `kind="handle"` → call `core.youtube_meta.resolve_handle_to_channel_id` on a worker thread → continue as `channel_id`.
  - `kind="channel_id"` → fetch preview via `fetch_channel_preview` (worker thread) → render preview card (artwork, title, video_count) + backfill segmented `[ All ] [ Only new ] [ Last 20 ] [ Last 50 ]` (default `Only new`).
  - `kind="video"` → check if any subscribed YouTube show matches via `--print channel_id`; if yes, offer to attach; else create a one-off `youtube-misc` show.

If `not ytdlp.is_installed()`, the mode shows a "Install yt-dlp" button that opens `YtdlpInstallDialog(mode="install")`. After `finished_install(True)`, retry the parse.

`_do_save` extension: build a `Show(source="youtube", rss=rss_url_for_channel_id(cid), slug=slugify(preview["title"]), title=preview["title"], artwork_url=preview["artwork_url"])` + a backfill enqueue using `enumerate_channel_videos`.

**Step 4: Verify + suite.**

**Step 5: Commit.**

```bash
git add ui/add_show_dialog.py tests/test_add_show_dialog_youtube.py
git commit -m "feat(add-show): YouTube URL mode (channel + video) with preview"
```

---

## Task 13: Worker thread — yt-dlp self-update on launch + weekly

Hook `core.ytdlp.self_update()` into the existing app launch path (`ui/main_window.py` or `ui/app_context.py` startup). Cadence: on launch if YouTube is enabled AND last update > 7 days ago.

**Files:**
- Modify: `ui/main_window.py` (or app startup module).
- Modify: `core/models.py` `Settings` — add `ytdlp_last_self_update_at: str = ""` (ISO date).
- Test: `tests/test_ytdlp_self_update_cadence.py` (new).

**Step 1: Failing tests.**

```python
def test_self_update_runs_when_never_run(monkeypatch, tmp_path):
    from core.models import Settings
    from ui.main_window import maybe_self_update_ytdlp  # extract the helper
    s = Settings(sources_youtube=True, ytdlp_last_self_update_at="")
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr("core.ytdlp.self_update",
                        lambda: called.__setitem__("ran", True))
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert called["ran"]


def test_self_update_skipped_within_7_days(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from core.models import Settings
    from ui.main_window import maybe_self_update_ytdlp
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    s = Settings(sources_youtube=True, ytdlp_last_self_update_at=recent)
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr("core.ytdlp.self_update",
                        lambda: called.__setitem__("ran", True))
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert not called["ran"]


def test_self_update_skipped_when_youtube_disabled(monkeypatch):
    from core.models import Settings
    from ui.main_window import maybe_self_update_ytdlp
    s = Settings(sources_youtube=False)
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr("core.ytdlp.self_update",
                        lambda: called.__setitem__("ran", True))
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert not called["ran"]
```

**Step 2: Verify fail.**

**Step 3: Implement.**

Add to `ui/main_window.py`:

```python
from datetime import datetime, timezone, timedelta
from core import ytdlp
from core.sources import youtube_enabled


def maybe_self_update_ytdlp(settings, save) -> None:
    if not youtube_enabled(settings):
        return
    if not ytdlp.is_installed():
        return  # no install yet; nothing to update
    last = settings.ytdlp_last_self_update_at
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - last_dt < timedelta(days=7):
                return
        except ValueError:
            pass
    try:
        ytdlp.self_update()
        settings.ytdlp_last_self_update_at = datetime.now(timezone.utc).isoformat()
        save()
    except Exception:
        # Silent: failure shows up next time YouTube action is attempted.
        pass
```

Call once at the end of `MainWindow.__init__` (after the main loop is up): `QTimer.singleShot(2000, lambda: maybe_self_update_ytdlp(self.ctx.settings, self.ctx.save_settings))`.

**Step 4: Verify + suite.**

**Step 5: Commit.**

```bash
git add ui/main_window.py core/models.py tests/test_ytdlp_self_update_cadence.py
git commit -m "feat(ytdlp): self-update on launch when >7 days stale"
```

---

## Task 14: Per-channel transcript-source override in Show Details

**Files:**
- Modify: `ui/show_details_dialog.py`.
- Test: `tests/test_show_details_dialog_youtube.py` (new).

**Step 1: Failing test.**

```python
def test_show_details_dropdown_for_youtube_show(qtbot):
    from ui.show_details_dialog import ShowDetailsDialog
    from core.models import Show
    show = Show(slug="ch", title="Channel", rss="...", source="youtube",
                youtube_transcript_pref="captions")
    dlg = ShowDetailsDialog(show, _ctx())
    qtbot.addWidget(dlg)
    assert dlg.transcript_pref_combo is not None
    assert dlg.transcript_pref_combo.currentText().startswith("Captions first")


def test_show_details_dropdown_hidden_for_podcast(qtbot):
    from ui.show_details_dialog import ShowDetailsDialog
    from core.models import Show
    show = Show(slug="p", title="P", rss="https://feed", source="podcast")
    dlg = ShowDetailsDialog(show, _ctx())
    qtbot.addWidget(dlg)
    assert not getattr(dlg, "transcript_pref_combo", None) or not dlg.transcript_pref_combo.isVisible()
```

**Step 2-4:** Add the combo box conditionally; wire `currentTextChanged` to update `show.youtube_transcript_pref` and save the watchlist.

**Step 5: Commit.**

```bash
git add ui/show_details_dialog.py tests/test_show_details_dialog_youtube.py
git commit -m "feat(show-details): YouTube transcript-pref dropdown per channel"
```

---

## Task 15: End-to-end smoke test (offscreen Qt)

Drives the whole add-channel flow with all subprocess calls mocked, asserting state.sqlite + watchlist.yaml end up consistent.

**Files:**
- Create: `tests/test_youtube_e2e_smoke.py`.

**Step 1: Test.**

```python
def test_add_youtube_channel_writes_watchlist_and_enqueues(qtbot, tmp_path, monkeypatch):
    # Mock yt-dlp installed; mock fetch_channel_preview + enumerate_channel_videos.
    monkeypatch.setattr("core.ytdlp.APP_SUPPORT", tmp_path)
    (tmp_path / "bin").mkdir(parents=True)
    (tmp_path / "bin" / "yt-dlp").write_text("#!/bin/sh\n")
    (tmp_path / "bin" / "yt-dlp").chmod(0o755)
    monkeypatch.setattr("core.youtube_meta.fetch_channel_preview",
        lambda cid: {"channel_id": cid, "title": "Channel X",
                     "video_count": 50, "artwork_url": ""})
    monkeypatch.setattr("core.youtube_meta.enumerate_channel_videos",
        lambda cid, limit=None: [{"id": f"v{i}", "title": f"Ep {i}",
                                  "timestamp": 1700000000 + i * 100}
                                 for i in range(20)])
    # Drive: open AddShowDialog → YouTube mode → paste channel URL →
    # click Add. Then assert watchlist contains a Show(source="youtube")
    # and state.sqlite has 20 pending episodes.
```

**Step 2-5:** Standard TDD loop; commit.

```bash
git add tests/test_youtube_e2e_smoke.py
git commit -m "test(youtube): e2e smoke — add channel writes watchlist + queue"
```

---

## Task 16: CHANGELOG + version bump → v1.2.0

**Files:**
- Modify: `CHANGELOG.md`.
- Modify: `core/version.py` (single-source version).

**Step 1: No tests.**

**Step 2: Edit `core/version.py`** — bump to `1.2.0`.

**Step 3: Add `CHANGELOG.md` entry:**

```markdown
## v1.2.0 — 2026-04-XX (YouTube ingestion)

### Added
- **YouTube channels as first-class shows.** Subscribe to a channel,
  paragraphos polls its hidden RSS feed daily and transcribes new
  videos. Backfill via yt-dlp.
- **Ad-hoc YouTube videos.** Paste a video URL in the Add Podcast
  dialog → attach to a subscribed channel or create a one-off.
- **Captions-first transcript.** Uploader-provided captions are
  fetched and converted (VTT → SRT) instantly; whisper takes over
  when no captions are available.
- **Per-channel transcript-source override** in Show Details:
  Captions / Always whisper / Use auto-captions if no manual.
- **yt-dlp lazy install + weekly self-update.** Installed to
  ~/Library/Application Support/Paragraphos/bin/yt-dlp on first
  YouTube use; `yt-dlp -U` runs once a week.
- **Sources filter in Settings.** Uncheck YouTube to hide all
  YouTube UI and skip the yt-dlp install.
```

**Step 4: Run `.venv/bin/python -m pytest -q && .venv/bin/python -m pytest tests/integration -m integration -q` if integration is set up.**

**Step 5: Commit + tag.**

```bash
git add CHANGELOG.md core/version.py
git commit -m "chore(release): v1.2.0 — YouTube ingestion"
git tag v1.2.0
```

---

## Verification before declaring Theme A done

- `.venv/bin/python -m pytest -q` — all green, no skips that didn't exist before.
- Manual: open the app, Settings → uncheck YouTube → confirm Add dialog hides the 4th mode.
- Manual: with YouTube enabled, paste a real channel URL (e.g. a small German podcast YouTube re-upload) → preview renders → Add → 1 video transcribes via captions in <5 s, 1 via whisper.
- Manual: paste a video with no captions → whisper-fallback path completes, `.md` writes with `transcript_source: whisper`.
- Manual: open the produced `.md` in Obsidian — frontmatter, body, `[Watch on YouTube]` link all present.

@superpowers:verification-before-completion before claiming any of the above.
