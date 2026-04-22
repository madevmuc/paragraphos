# YouTube ingestion + Auto-update — Design

**Date:** 2026-04-22
**Status:** Brainstorm approved; ready for implementation plan.
**Target version:** v1.2.0

Two independent features bundled in one design because both expand
paragraphos beyond its v1.x "podcasts only, manual updates" scope.

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
```

### Migration

- Existing settings file gains 4 new keys with safe defaults
  (`sources_podcasts=true`, `sources_youtube=true`,
  `update_check_enabled=true`, `skipped_version=""`).
  Backfilled on load like the v1.1.9 `setup_completed` migration.
- No state-schema changes for shows or episodes (the YouTube source
  marker lives in frontmatter, not SQLite).

### Out of scope for v1.2

- In-app YouTube search (paste only).
- Live caption streaming during transcription.
- Browser extension hand-off.
- Code signing / notarisation.
- Sparkle framework. Custom mechanism is small and avoids the dep.
- Delta updates. Full DMG re-download per release; ~50 MB is fine.

### Phasing

Both features are independent. Suggested commit order in the
implementation plan:

1. Settings → Sources + Updates sections (foundation).
2. yt-dlp lazy-installer + Sources gating.
3. YouTube channel add (RSS poll + backfill via yt-dlp).
4. YouTube transcript path (captions-first, whisper-fallback).
5. Auto-update check + modal.
6. Auto-update install flow + restart handshake.

Ship as **v1.2.0** with both features.
