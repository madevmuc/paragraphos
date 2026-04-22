# YouTube ingestion + Auto-update — Design

**Date:** 2026-04-22
**Status:** Brainstorm approved; ready for implementation plan.
**Target version:** v2.0.0

A bundled major release expanding paragraphos beyond its v1.x
"podcasts only, manual updates" scope. **No LLM dependencies** —
every feature works offline against local artefacts or whisper.cpp
native capabilities.

Themes:

1. **YouTube ingestion** — channels as first-class shows + ad-hoc videos.
2. **Auto-update** — non-blocking prompt + atomic install.
3. **Performance** — finish the two whisper-side perf items left over from old Phase 1.5.
4. **Knowledge/discovery** — FTS5 search, OPML import/export, ID3 chapter parsing, smart playlists.
5. **Power-user wiring** — speaker diarization (whisper.cpp native), episode-finish webhook.

---

## Feature A — YouTube ingestion

### Goal

Treat YouTube channels as first-class shows alongside podcasts, plus
support ad-hoc one-off video transcription. New videos are picked up
automatically (channel polling) or on demand (URL paste). Transcripts
land in the same `raw/transcripts/<slug>/` location as podcast
episodes so the knowledge-hub compile pipeline ingests them
identically.

### Mental model

- **Channels = shows.** A subscribed YouTube channel appears in the
  Shows tab next to podcast shows, with a small `▶ YouTube` /
  `🎙 Podcast` pill to distinguish source.
- **Videos = episodes.** Same status machine (`pending → downloading →
  downloaded → transcribing → done`), same Queue tab, same retention.
- **Ad-hoc videos** are added as one-off entries against a synthetic
  `youtube-misc` show, or attached to the right channel if it's
  already subscribed.

### Transcript-source priority

Default: **captions-first, whisper-fallback.**

1. If uploader-provided manual captions exist → fetch via yt-dlp,
   convert VTT → SRT + plaintext markdown. Done in ~1 s.
2. Else → audio-only download + whisper transcribe (existing pipeline).
3. YouTube auto-captions are **not** used by default (low quality, no
   punctuation). Opt-in tier behind a global setting.

**Per-channel override** in Show Details: dropdown
`Prefer captions / Always whisper / Use auto-captions if no manual`.

### Polling mechanism

- **Routine polling: hidden RSS feed.**
  `https://www.youtube.com/feeds/videos.xml?channel_id=UC...`
  No API key, no rate limit, returns latest ~15 videos.
  Reuses `core/rss.py` and the conditional-GET (ETag) machinery.
- **Initial backfill: yt-dlp `--flat-playlist`** on the channel URL.
  Enumerates the full upload history. User picks the slice via the
  same `[ All ] [ Only new ] [ Last 20 ] [ Last 50 ]` segmented control
  the existing Add-Podcast Mode B uses.

### Tooling: yt-dlp

- Bundled initially via `pip install yt-dlp` into the py2app build,
  but **installed to a user-writable location** on first YouTube
  use: `~/Library/Application Support/Paragraphos/bin/yt-dlp`.
- Self-updates via `yt-dlp -U` on app launch + weekly cadence.
  Update progress shown in a non-blocking popup
  ("Updating yt-dlp to keep YouTube downloads working… 2.3 / 5.1 MB").
  Cancellable; failure disables YouTube until next attempt, doesn't
  block the rest of the app.
- **Lazy install**: yt-dlp is only fetched on first YouTube action
  (adding a channel, pasting a video URL). Podcast-only users never
  touch it.

### Source filter (Settings)

New Settings section **Sources**:

```
Sources
  [x] Podcasts
  [x] YouTube
```

≥1 must be checked. Unchecking YouTube hides all YouTube UI surfaces
and skips the yt-dlp lazy-install. Default: both checked.

### UX surfaces

- **Add dialog** (`ui/add_show_dialog.py`): existing 3-mode segmented
  control gains a 4th mode `[ YouTube URL ]`. Paste a channel URL
  (`youtube.com/@handle` or `/channel/UC...`) → preview card with
  thumbnail · title · subscriber count · video count, plus the
  backfill segmented control. Paste a video URL → confirms attaching
  to the matching subscribed channel or creates a one-off.
- **No in-app YouTube search in v1.2** — paste-only. yt-dlp-based
  search is tracked as a fast follow.
- **Shows tab**: source pill in title cell. Existing filters
  (enabled / has_pending / etc.) gain a "Source: podcast | youtube |
  any" filter.
- **Show Details**: feed URL field accepts the YouTube channel URL;
  the `Prefer captions / Always whisper / Auto-captions` dropdown
  appears only for YouTube shows.

### Storage layout

Identical to podcasts. Channel slug derived via the existing
`core.sanitize.slugify()` helper from the channel title.

```
raw/transcripts/<channel-slug>/
  YYYY-MM-DD_HHMM_<video-title-slug>.md
  YYYY-MM-DD_HHMM_<video-title-slug>.srt
```

Frontmatter additions for YouTube items:

```yaml
source: youtube
youtube_id: dQw4w9WgXcQ
youtube_url: https://youtu.be/dQw4w9WgXcQ
channel_id: UCuAXFkgsw1L7xaCfnd5JJOw
transcript_source: captions | auto-captions | whisper
```

Body template gains a `[Watch on YouTube](https://youtu.be/<id>)` link
analogous to the podcast `audio_url`.

### Audio extraction (whisper-fallback path)

`yt-dlp -f bestaudio --extract-audio --audio-format mp3 --audio-quality 0`
→ MP3 lands in the same per-show working directory as podcast MP3s,
hands off to the existing transcribe worker unchanged. MP3 retention
setting applies the same way.

### Error handling

- yt-dlp not installed and YouTube action requested → trigger
  lazy-install with progress popup; queue the action behind it.
- yt-dlp install fails → mark all YouTube shows as
  `feed: unreachable (yt-dlp install failed)`, surface in Failed tab,
  retry on next launch.
- Channel RSS returns 404 (channel deleted/private) → mark show
  `feed: unreachable`, same handling as a dead podcast feed.
- Video unavailable / age-restricted / region-locked → fail the
  individual episode with a humanised reason
  (`youtube: age-restricted`, `youtube: region-locked DE`, etc.) so
  the Failed tab reads like the existing whisper failures.
- Caption fetch fails despite captions being advertised → fall back
  to whisper automatically, log the fallback.

### Testing

- Unit: caption VTT → SRT conversion, channel-slug derivation, URL
  parsing (handle vs channel-id vs video URL forms).
- Integration: a fixture channel with one short Creative-Commons
  video, end-to-end through caption-first and whisper-fallback paths.
  Marked `@pytest.mark.integration`, opt-in.
- Offscreen Qt smoke: Add-dialog YouTube mode, Settings Sources
  section, Show Details YouTube override.

---

## Feature B — Auto-update

### Goal

Keep installed paragraphos copies current without manual DMG
re-downloads. User sees a non-blocking "new version available" prompt
with the changelog, can install immediately, defer, or skip the
specific version.

### Distribution

GitHub Releases. Each tagged release ships:

- `Paragraphos-<version>.dmg`
- `Paragraphos-<version>.dmg.sha256`
- `latest.json` manifest (overwritten on each release):

```json
{
  "version": "1.2.0",
  "released_at": "2026-04-30T12:00:00Z",
  "min_macos": "13.0",
  "dmg_url": "https://github.com/.../Paragraphos-1.2.0.dmg",
  "sha256": "abc123...",
  "changelog": "## v1.2.0\n\n### Added\n- YouTube ingestion\n..."
}
```

### Check cadence

- On app launch (after main window is up, non-blocking).
- Every 24 h while running (timer in main loop).
- Manual: Settings → "Check for updates now" button.

### UX

Non-blocking modal `UpdateAvailableDialog`:

- Header: `Paragraphos v1.2.0 is available (you have v1.1.9)`
- Body: rendered changelog markdown for every version between current
  and latest, scrollable.
- Buttons: **Install now** · **Remind me later** · **Skip this version**

State persisted in `Settings`:

- `last_update_check_at`
- `skipped_version` (string; suppresses prompts until a newer version
  appears)
- `update_check_enabled` (bool, default true; Settings toggle)

### Install flow

Modal `UpdateProgressDialog` with phased status line:

1. `Downloading 24 / 58 MB · 3.2 MB/s · ~10 s left` (cancellable)
2. `Verifying SHA256` (~1 s, non-cancellable)
3. `Mounting DMG`
4. `Replacing app`
5. `Restart required` → buttons **Restart now** / **Restart later**

Mechanism: download to
`~/Library/Application Support/Paragraphos/updates/`, verify SHA256,
`hdiutil attach`, `rsync -a` the new `.app` over the running one's
location, `hdiutil detach`. macOS keeps the running binary mapped, so
the replace is safe; the new code only takes effect on next launch.

If "Restart later" is chosen, no further prompt — the update is
already on disk and active on next manual quit + relaunch.

### Code signing

paragraphos is currently unsigned. Auto-installed updates therefore
trigger a Gatekeeper warning on next launch. v1.2 ships with a
documented workaround in the success dialog:

> Update installed. On first launch you may see a "Paragraphos.app is
> from an unidentified developer" prompt — right-click the app in
> Finder and choose **Open** to dismiss it permanently.

Code signing + notarisation is tracked as a follow-up (Apple Developer
ID, $99/yr, build pipeline changes). Not blocking this feature.

### Error handling

- Network failure during check → silent retry next cadence.
- Download failure → user-visible error in the progress dialog with
  a Retry button. Partial download in `updates/` cleaned up.
- SHA mismatch → abort, surface "Update file corrupted; please try
  again", do NOT install.
- Replace failure (permission denied if app is in `/Applications`
  without write perms) → fall back to "Open download in Finder" so
  the user can drag-replace manually. Same outcome, more steps.

### Testing

- Unit: `latest.json` parsing, version comparison
  (semver via `packaging.version`), skipped-version logic.
- Integration: a local fake-server fixture serving `latest.json` +
  a tiny dummy DMG, drive the full flow with Qt offscreen.
- Manual: real GitHub release, real DMG, on a clean macOS install.

---

---

## Feature C — Performance: finish old Phase 1.5

Two whisper-side wins from the original v0.5.1 perf phase that never
landed. Verified open in current code. Both opt-in toggles, no
default behaviour change.

### C1 — whisper-cli `-p N` multi-processor split

- File: `core/transcriber.py`, `ui/settings_pane.py`.
- whisper-cli's `-p N` flag splits audio into N chunks processed in
  parallel on separate threads. ~2× speedup on a 4-perf-core
  M-series for hour-long episodes.
- Setting: `whisper_processors` (int, default 1; UI slider 1–8).
  Hint: "Higher = faster on long episodes, more CPU heat."
- Gated behind opt-in to protect users on small Macs.
- Test: assert `-p N` flag present iff setting > 1.

### C2 — Stream-to-whisper (no intermediate MP3 file)

- File: `core/pipeline.py`, `core/downloader.py`, `core/transcriber.py`.
- Pipe `httpx.stream` output directly to whisper-cli via `-f -`
  (stdin). Saves one disk round-trip; only profitable for ≥100 MB
  episodes.
- Setting: `stream_mode` (bool, default off).
- Trade-off: breaks MP3-retention (the file was never on disk).
  Document in Settings hint: "Saves disk I/O. Disables MP3 retention
  for streamed episodes."

---

## Feature D — Knowledge & discovery

### D1 — Full-text search across transcripts (FTS5)

- File: `core/state.py` (FTS5 virtual table), new `core/search.py`,
  new `ui/search_palette.py`.
- SQLite FTS5 virtual table `transcript_fts(guid, show_slug, title,
  body, ts)`. Populated on episode `done` (insert) and re-transcribe
  (replace). Initial backfill via library scan.
- `core/search.py`:
  - `search(query, *, show=None, since=None, limit=50)` returns ranked
    hits with snippets (FTS5 `snippet()` function).
  - `search_metadata(filters)` for status/date queries (smart
    playlists' non-FTS half).
- `ui/search_palette.py`: `⌘F` opens a Spotlight-style modal palette
  over the main window. Live results as user types. Click → opens the
  `.md` in Obsidian (existing helper).
- Index size estimate: ~30% of transcript markdown size on disk;
  ~50 MB for a 5,000-episode vault.
- Test: insert/update/delete keep index in sync; query ranks recent
  matches above older ones for tie-breaks.

### D2 — Smart playlists / saved searches

- File: new `core/smart_playlists.py`, `ui/smart_playlists_tab.py`.
- A "smart playlist" is a saved query: combination of metadata
  filters (status, show, date range, has_failed, etc.) and an
  optional FTS5 text term.
- Schema: `state.smart_playlists(id, name, query_json, created_at,
  updated_at)`. `query_json` is a structured filter spec.
- New sidebar entry **Playlists** below Library. Each playlist row
  shows count + last-run timestamp. Click → table of matching
  episodes (read-only view, same columns as Queue).
- Built-ins shipped: "Failed in last 7 days", "Done this week",
  "Pending > 2 days old".
- User-created via "+ New playlist" → modal with filter form +
  optional search term + name field.
- Depends on D1 for the text-term filter; metadata-only playlists
  work without FTS5.

### D3 — OPML import/export

- File: new `core/opml.py`, `ui/opml_dialog.py`, hook in tray menu
  (slot already exists per design-handoff brief).
- **Import**: parse OPML 2.0, extract `<outline xmlUrl="..."/>`
  entries, run each through the existing add-show flow with
  Backlog=`Only new` as default. Show a summary dialog: N added,
  M skipped (already subscribed), K failed (bad feed).
- **Export**: write `paragraphos-shows.opml` containing all enabled
  podcast shows (NOT YouTube — OPML is podcast-spec). User picks
  destination via standard save dialog.
- Test: round-trip a 50-show OPML, assert all imported with correct
  RSS URLs.

### D4 — MP3 ID3 chapter parsing

- File: `core/id3_chapters.py` (new), hook in `core/transcriber.py`
  post-process step.
- Many podcasts ship ID3v2 CHAP/CTOC frames with chapter markers
  (title + start_ms). Parse with `mutagen` (new dep, lightweight).
- After transcription, walk SRT timestamps and inject
  `## Chapter N: <title>` markdown headings at the matching offsets.
- Frontmatter gains `chapters: [{title, start_ms}, ...]` for
  downstream tooling.
- Silently no-op when no chapters present.
- Test: fixture MP3 with 3 chapters → 3 headings in output `.md` at
  correct line offsets.

---

## Feature E — Power-user wiring

No LLM dependencies. Speaker diarization runs on whisper.cpp's
native tinydiarize support; webhook is plain HTTP.

### E1 — Speaker diarization

- File: `core/transcriber.py` (whisper-cli flags), settings.
- whisper.cpp supports `--diarize` with the **tinydiarize** model
  (`small.en-tdrz`). When enabled, output SRT lines get
  `[SPEAKER_00]`, `[SPEAKER_01]` prefixes.
- Setting: `diarize_enabled` (bool, default off; per-show override
  in Show Details). Auto-fetches the tinydiarize model on first use
  (same flow as the main whisper model download).
- Limitation: tinydiarize is English-only. For non-English shows the
  toggle is greyed out with hint "tinydiarize: English only."
- The `.md` body retains speaker prefixes; SRT keeps them in line
  text. No new frontmatter field.
- Test: assert `--diarize -mt <tdrz-model>` flags only when toggle
  on; assert `[SPEAKER_*]` prefixes preserved through MD render.

### E2 — Episode-finish webhook

- File: new `core/webhooks.py`, settings extension.
- Setting: `webhook_url` (string, optional). When set, on each
  episode `done` transition, POST a JSON payload:

  ```json
  {
    "event": "episode.done",
    "show": {"slug": "...", "title": "...", "source": "podcast|youtube"},
    "episode": {"guid": "...", "title": "...", "published_at": "...",
                "duration_s": 3600, "transcript_path": "...",
                "audio_url": "...",
                "chapters": [{"title": "...", "start_ms": 0}, ...]}
  }
  ```
- One retry with 30 s delay on 5xx / network failure; 4xx logs and
  drops. Never blocks the pipeline.
- Optional HMAC signing: `webhook_secret` (Keychain). Header
  `X-Paragraphos-Signature: sha256=<hex>` with the request body.
- Test: mocked HTTP server receives expected payload + signature.

---

## Cross-cutting

### Settings additions

```
Sources
  [x] Podcasts
  [x] YouTube

Updates
  [x] Check for updates automatically
  [ Check now ]   Last checked: 2026-04-22 14:32

YouTube (visible only when Sources → YouTube checked)
  Default transcript source:  ( ) Captions first, whisper fallback
                              ( ) Always whisper
                              ( ) Use auto-captions if no manual
  yt-dlp version: 2026.03.30  [ Update now ]

Performance
  Whisper processors:  [—————●——] 4    (1 = single, 8 = max)
  [ ] Stream-mode (skip MP3 file, requires retention off)

Discovery
  [x] Index transcripts for full-text search
  [ Rebuild index ]   Last indexed: 2026-04-22 14:32

Transcripts
  [ ] Speaker diarization (English only)
  [ ] Parse MP3 chapter markers (ID3) into headings

Webhooks
  Episode-finish URL: [_______________________]
  HMAC secret: [keychain entry]    [ Test ]
```

### State / schema additions

- **`state.transcript_fts`** — FTS5 virtual table (D1).
- **`state.smart_playlists`** — id, name, query_json, created_at,
  updated_at (D2).
- **Settings keys** (all backfilled on load like v1.1.9
  `setup_completed`):
  `sources_podcasts`, `sources_youtube`,
  `update_check_enabled`, `skipped_version`,
  `youtube_default_transcript_source`,
  `whisper_processors`, `stream_mode`,
  `fts_enabled`,
  `diarize_enabled`, `id3_chapters_enabled`,
  `webhook_url`, `webhook_secret_keychain_id`.
- **Frontmatter additions**: `source`, `youtube_id`, `youtube_url`,
  `channel_id`, `transcript_source` (YouTube items);
  `chapters`, `chapter_source` (D4).
- **New deps**: `mutagen` (D4 ID3 parsing), `keyring` (E2 webhook
  secret + future remote-API keys). yt-dlp lazy-installed at
  runtime, not a build dep.

### Out of scope for v2.0

- In-app YouTube search (paste only; fast follow).
- Live caption streaming during transcription.
- Browser extension hand-off.
- Code signing / notarisation (deferred; documented Gatekeeper
  workaround in auto-update success dialog).
- Sparkle framework. Custom mechanism is small and avoids the dep.
- Delta updates. Full DMG re-download per release; ~50 MB is fine.
- Any LLM-driven feature (entity extraction, summarisation,
  LLM-driven chapter detection). Explicitly excluded — no LLM
  dependencies in v2.0.
- Cross-device sync.
- Mobile companion.

### Phasing

Suggested commit order in the implementation plan, grouped by
theme. Each commit is independently shippable; intermediate
versions can ship as v1.2.x → v1.9.x if desired before tagging
v2.0.

**Foundation**

1. Settings → Sources + Updates + Performance + Discovery +
   Transcripts + Webhooks sections (UI scaffolding only, no-op
   toggles).

**Theme A — YouTube ingestion**

2. yt-dlp lazy-installer + Sources gating + self-update popup.
3. YouTube channel add (hidden RSS poll + backfill via
   `yt-dlp --flat-playlist`).
4. YouTube transcript path (captions-first VTT→SRT, whisper
   fallback, per-channel override).

**Theme B — Auto-update**

5. `latest.json` manifest fetch + version compare + non-blocking
   modal + skip-this-version persistence.
6. Download + SHA256 verify + atomic rsync replace + restart
   handshake. Document Gatekeeper workaround.

**Theme C — Performance**

7. C1: whisper-cli `-p N` multi-processor split (opt-in slider).
8. C2: Stream-to-whisper opt-in mode.

**Theme D — Knowledge & discovery**

9. D1: SQLite FTS5 virtual table + backfill scan + `core/search.py`.
10. D1 (cont.): `⌘F` search palette UI.
11. D2: Smart-playlists schema + sidebar entry + built-in playlists
    + new-playlist modal.
12. D3: OPML import/export + tray-menu hook.
13. D4: ID3 chapter parsing via `mutagen` + heading injection +
    frontmatter `chapters` field.

**Theme E — Power-user wiring**

14. E1: Speaker diarization toggle + tinydiarize model auto-fetch
    + per-show override.
15. E2: Episode-finish webhook + HMAC signing + retry policy.

Ship as **v2.0.0** with all of the above. Themes A and B can ship
earlier as v1.2.0 if it's useful to release them first; the rest
follow as v1.3.x → v2.0.0.
