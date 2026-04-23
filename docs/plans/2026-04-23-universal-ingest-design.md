# Universal ingest — Design

**Date:** 2026-04-23
**Status:** Brainstorm approved.
**Target release:** v1.3.0 — "Universal ingest" — single release behind no flag.

Extend Paragraphos's ingest surface beyond RSS podcasts and YouTube
channels to any audio/video source the user has on hand. Three entry
points: drag-drop of files or pasted URLs into an in-app drop zone, a
watched folder that auto-picks up new files, and a one-shot folder
import for backfilling an existing pile.

Search and analysis belong to the downstream LLM / wiki-compile layer.
Paragraphos's job is ingestion + transcription.

---

## 1. Scope

In:

1. **Drop zone** — Qt widget on the Shows page that accepts drag-drop
   of local media files or a pasted URL. A global drag-drop handler on
   the main window dispatches to the same path so drops anywhere work.
2. **Watch folder** — configurable path (default
   `~/Paragraphos/to-be-transcribed/`); new files landing in
   top-level subfolders auto-queue against a show derived from the
   subfolder name.
3. **Folder import** — `File → Import folder…` menu action; one-shot
   scans a chosen directory and queues every recognised file.

Out (all deferred to the LLM/wiki layer or later phases):

- Full-text search across transcripts
- Speaker diarization
- Semantic / embeddings search
- Web UI / headless daemon
- Code signing + notarisation

## 2. Data model — synthetic shows

All three paths reuse the existing `shows → episodes` model. No new
top-level concept.

Shows gain a `source_type` value extending the v1.2.0 sources
mechanism:

```
podcast | youtube | local-folder | local-drop | url
```

Show-slug derivation per path:

- **Watch folder** — top-level subfolder under the watched root
  becomes the show slug. `~/…/to-be-transcribed/zoom/*.mp4` → show
  `zoom`. Files placed at the root (no subfolder) go to a default
  `files` show.
- **Drop-zone file** — default show `files`; drop-time dropdown
  offers existing local shows so the user can redirect in one click.
- **Drop-zone URL** — yt-dlp's extractor returns uploader / channel;
  use that as the show slug when confident, else `web` catch-all.
  (Mirrors the YouTube path from v1.2.0.)
- **Folder import** — modal prompts for a slug, prefilled with the
  folder's basename.

### Dedup + GUID

- Files: `sha256:<hex>` of content. A fast path keyed on
  `(abs_path, size, mtime)` in `state.meta["filehash:…"]` skips
  rehashing on re-seen paths. Hash collision on distinct files is
  treated as same-content (SHA-256 collision is not a realistic
  concern).
- URLs: `<extractor>:<id>` from yt-dlp; fallback the URL itself when
  no ID is available.

### Supported formats

Anything ffmpeg can decode: `.mp3 .m4a .m4b .wav .aiff .flac .ogg
.opus .mp4 .mov .mkv .webm .avi .wmv …`. Pipeline pre-normalises
non-WAV inputs to a temp WAV via ffmpeg; existing transcribe call is
unchanged. ffmpeg is already a declared dep.

## 3. New modules

### `core/local_source.py`

```python
def ingest_file(path: Path, show_slug: str | None = None) -> EpisodeDict
def ingest_url(url: str, show_slug: str | None = None) -> EpisodeDict
def ingest_folder(path: Path, show_slug: str | None = None,
                  recursive: bool = True) -> list[EpisodeDict]
def sha256_of(path: Path) -> str   # size+mtime cache shortcut
```

Each returns an episode dict ready for the existing upsert path. URL
ingest delegates to the existing yt-dlp flow with the generic
extractor.

### `core/watch_folder.py`

```python
class WatchFolder:
    def __init__(self, root: Path): ...
    def start(self): ...   # wraps watchdog.Observer
    def stop(self): ...
```

- New-file events debounce 2 s to avoid racing partial writes.
- ffprobe gates queueing: the file must decode and have ≥1 audio
  stream; retries once after 5 s if ffprobe fails the first time.
- Root-disappearance (external drive unmount) mirrors the offline
  pattern from `core/connectivity.py` — pause that source + show
  banner, auto-resume on re-mount.

### `ui/drop_zone.py`

- `DropZone(QWidget)` card on the Shows page: icon, prompt text,
  URL line-edit. Accepts files via `QDragEnterEvent` /
  `QDropEvent`; text dropped on the URL field is URL-sniffed.
- `MainWindow` installs a global drop handler that forwards drops
  anywhere on the window to `DropZone`'s dispatcher.

### `ui/import_folder_dialog.py`

Modal with:

- Folder picker
- Show-slug field (prefilled from basename)
- Scan preview — "Found N supported files" (live as user changes
  path)
- Recursive checkbox (default on)
- Cancel / Import

### `ui/settings_pane.py` — new **Local sources** group

- Enable / disable watch folder (default off on fresh installs)
- Root path picker (default `~/Paragraphos/to-be-transcribed/`)
- Post-processing: keep in place (default) · move to `done/` sibling
  · delete. Chosen per watch-folder root.
- Max duration cap (default 4 h, configurable). Over-cap files go to
  Failed with a clear reason.

## 4. Data flow

```
 Drop file    Drop URL      Watch event     Folder import
     │            │               │                │
     ▼            ▼               ▼                ▼
 ingest_file  ingest_url      ingest_file     ingest_folder
     └────────────┴───────────────┴────────────────┘
                         │
                         ▼
  assign show_slug + GUID → episode row (status=pending)
                         │
                         ▼
  existing pipeline: (url → yt-dlp download)
                   | (file → copy or symlink to staging)
                   → ffmpeg normalise → whisper → render .md
```

For local files the existing `download_mp3` step is bypassed — a
small helper either symlinks or copies the source into staging,
respecting the existing MP3-retention setting.

## 5. Error handling

| Failure | Response |
|---|---|
| Unsupported format | Failed tab — "Unrecognised format (ffmpeg couldn't decode)" |
| No audio stream in video | Failed tab — "Video has no audio track" |
| File exceeds duration cap | Failed tab — "Exceeds duration cap (4 h) — change Settings → Local sources → max duration if intentional" |
| Partial / still-writing file | 2 s debounce + ffprobe gate; retries once after 5 s if ffprobe fails |
| Watch root unmounted | Banner + pause that source; auto-resume on re-mount |
| Hash collision (same SHA, different path) | Log + queue — content is identical |
| URL rejected by SSRF guard | Failed tab, existing error path |
| yt-dlp extractor unknown | Failed tab — "No extractor found for <url>" |

## 6. CLI parity

Extends the v1.2.0 full-CLI-for-agent surface:

```
paragraphos ingest file <path>   [--show <slug>]
paragraphos ingest url  <url>    [--show <slug>]
paragraphos ingest folder <path> [--show <slug>] [--recursive]
paragraphos watch add <path>
paragraphos watch remove <path>
paragraphos watch list
```

Each prints the resulting episode GUID(s) on stdout, newline-separated,
so agents can chain: `paragraphos ingest file foo.mp4 | paragraphos
wait-for`.

## 7. Testing

- **Unit**
  - `sha256_of` with mtime+size cache (first-call hashes, second-call
    shortcuts)
  - Show-slug derivation (watch subfolder, drop default, URL
    uploader, folder basename)
  - Folder walk with file-type filter + recursive flag
- **Integration (fixtures in `tests/integration/fixtures/`)**
  - 10 s `.wav` → pending → done, .md written
  - `.mp4` with audio → ffmpeg extract → whisper → .md
  - `.mp4` without audio → Failed with correct reason
  - Watch-folder new-file event → queue → done
  - URL via mocked yt-dlp generic extractor
- **UI smoke**
  - `DropZone` constructs
  - Accepts `QDropEvent` with local file URLs
  - Accepts pasted URL text via the URL line-edit
  - Dispatches to correct ingest function per payload type

## 8. Security delta

No new threat surface:

- Local files are user-initiated. No SSRF concern (no URLs fetched
  from file contents).
- Watch root must be a directory the user owns and can write to.
  Symlinks resolving outside the root are allowed (user's own files)
  but logged.
- URL-paste reuses the v1.2.0 SSRF-guarded yt-dlp generic path.
- `safe_path_within` still governs output path construction.

## 9. Rollout — single release v1.3.0

Commits, each independently green on tests:

1. `core/local_source.py` + sha256 + show-slug derivation
2. Pipeline hook — bypass `download_mp3` for local sources
3. ffmpeg-normalise wrapper (if not already implicit in the
   whisper-cli invocation)
4. `core/watch_folder.py` + Settings → Local sources group
5. `ui/drop_zone.py` on Shows page + global main-window drop
   handler
6. `ui/import_folder_dialog.py` + File menu entry
7. CLI `ingest` + `watch` subcommands
8. Docs + CHANGELOG entry

## 10. Open questions deferred past design

- Whether to expose the URL drop-zone as a distinct visual element
  or merge it into the existing "Add podcast / show…" segmented
  dialog — decided during implementation once the visual weight of
  the card is clear.
- Whether the watch folder's "move to `done/`" option should mirror
  the source folder structure or flatten — decided alongside
  settings UI polish.
