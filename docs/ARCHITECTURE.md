# Paragraphos — architecture at a glance

## Process model

Single Python 3.12 process:

- **Qt main thread**: all UI + `QSystemTrayIcon`.
- **APScheduler `BackgroundScheduler`**: daily cron, catch-up trigger.
  Runs in its own thread. Triggers are marshalled back to the GUI
  thread via `QTimer.singleShot(0, …)` before touching widgets.
- **`CheckAllThread` (QThread)**: the pipeline worker. One long-lived
  thread per run. Emits signals the UI + `QueueRunState` read.
- **`watchdog.Observer`**: filesystem watcher on `output_root`. Keeps
  the `LibraryIndex` in sync when transcripts are dropped in from
  outside.
- **`updater.check_for_update()` daemon**: ~1s of work on startup,
  surfaces a tray message when a newer GitHub release exists.

## Pipeline (one episode)

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. build_manifest_with_url()  ── httpx.get(feed, follow_redirects)  │
│    → list[{guid,title,pubDate,duration,episode_number,mp3_url,…}]   │
│    → canonical_url (persisted to watchlist.yaml if 301)             │
│                                                                     │
│ 2. LibraryIndex.dedup_check(guid,filename_key)                      │
│    hit → mark episode DONE, skip rest                               │
│                                                                     │
│ 3. download_mp3(url, dest)                                          │
│    ├─ safe_url()     reject file://, data:, private IPs            │
│    ├─ Content-Length cap 2 GB                                      │
│    ├─ retry 3× on 5xx/429/timeouts (1s, 5s, 20s)                   │
│    └─ Content-Type sniff must be audio/* or octet-stream           │
│                                                                     │
│ 4. transcribe_episode(mp3, slug, model, language, fast_mode, -p N) │
│    ├─ subprocess.run([whisper-cli, …], timeout=600)                │
│    ├─ hallucination guard (min_wpm)                                │
│    └─ write <slug>.md + <slug>.srt                                 │
│                                                                     │
│ 5. state.record_completion(guid, words, duration_sec)               │
│                                                                     │
│ 6. if retention: unlink the MP3                                    │
└──────────────────────────────────────────────────────────────────────┘
```

## State

```
~/Library/Application Support/Paragraphos/
├── watchlist.yaml          # human-editable list of shows
├── settings.yaml           # app preferences (auto-saved)
├── state.sqlite            # SQLite WAL, owns:
│   ├─ episodes (guid PK, show_slug, title, status, pub_date, mp3_url,
│   │           attempted_at, completed_at, word_count, duration_sec,
│   │           priority, error_text, …)
│   ├─ jobs     (historical run rows)
│   └─ meta     (key-value: queue_paused, feed_backoff_*, spotcheck_done_*, …)
├── model_hashes.yaml       # TOFU pins for whisper GGML files
├── library_cache.json      # mtime cache for LibraryIndex.scan()
└── logs/
    ├─ paragraphos.log[.YYYY-MM-DD]   # 90-day rotating file log
```

## Security posture

Full threat model in-app: **About → Security** tab. Summary:

- URL allow-list (http/https only) + SSRF guard (private-IP reject)
- Download size caps (MP3 2 GB, RSS 50 MB, HTML 10 MB)
- Path-traversal defence: sanitiser + `safe_path_within()`
- XXE-safe OPML (`defusedxml`)
- SQL-injection-impossible (parameterised `?`)
- No shell execution (`subprocess.run` with list args, never `shell=True`)
- TOFU SHA-256 for whisper models
- YAML via `safe_load` only

## Deployment topology

- Dev: `python setup.py py2app -A` builds an alias bundle that
  references the source tree. Live-reload after a restart.
- Distribution: `python setup-full.py py2app` builds a standalone
  310 MB .app. `scripts/build-dmg.sh` packages it into a DMG.
- CI: on every push, macOS runner runs ruff + pytest. On tag push,
  builds the full bundle + DMG and attaches them to a draft GitHub
  release.
- User's Mac: `/Applications/Paragraphos.app`. First launch walks
  through the deps wizard, then everything lives in
  `~/Library/Application Support/Paragraphos/`.
