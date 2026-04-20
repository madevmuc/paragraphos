# Paragraphos Roadmap — v0.5 → v1.0

> **For Claude:** REQUIRED SUB-SKILL: `superpowers:executing-plans`.

**Scope:** everything from the 2026-04-20 improvement brainstorm **except**:
- #7 LLM summarisation via Ollama
- #8 Full-text search across transcripts
- #16 Code signing + notarisation

**Excluded because:** they need separate architectural decisions (Ollama
pick, FTS5 schema, Apple Developer ID). They'll get their own plans.

---

## Phase 0 — Repo extraction (DONE before this plan lands)

Paragraphos moves out of `knowledge-hub/` into its own repo at
`/Users/matthiasmaier/dev/paragraphos/`. History preserved via
`git subtree split`. Side fixes:

- `scripts_legacy_shows` snapshots the legacy SHOWS whisper_prompts into
  `data/default_prompts.yaml` (bundled with the repo), falls back to the
  old `../transcribe.py` import only while still in-tree.
- `about_dialog.CHANGELOG_PATH` becomes relative to the paragraphos repo
  root, not knowledge-hub.
- `main_window.LAST_COMPILED` comes from a new
  `Settings.knowledge_hub_root` field (default `~/dev/knowledge-hub`,
  user-overridable). Banner hides if path doesn't exist.

After Phase 0 the code in `knowledge-hub/scripts/paragraphos/` is removed
and `knowledge-hub/CLAUDE.md` gets a one-liner pointing at the new repo.

---

## Phase 1 — Reliability (Tier 1, v0.5.0)

### Task 1.1: whisper-cli timeout
- File: `core/transcriber.py`
- `subprocess.run(cmd, capture_output=True, text=True, timeout=600)`
  (10 min — a 60-min podcast at ~1.5× realtime should finish in <6 min
  on M2 Pro, so 10 is generous).
- Catch `subprocess.TimeoutExpired`, kill the child, raise
  `TranscriptionError("whisper-cli timed out after 600 s — mp3=…")`.
- Test: mock `subprocess.run` to raise `TimeoutExpired`, assert
  `TranscriptionError` with useful message.

### Task 1.2: download retry with exponential backoff
- File: `core/downloader.py`
- Wrap the `httpx.stream` block in a retry loop: 3 attempts, delays
  `(1, 5, 20)` s. Retry on `httpx.HTTPError` and 5xx HTTP status.
- Do NOT retry 4xx (404, 403) — episode is permanently gone, fail fast.
- Test: mock `httpx.stream` to raise twice then succeed; assert single
  final success. Also: 4xx should not trigger retry.

### Task 1.3: real whisper model SHA256 digests
- File: `core/security.py`, `MODEL_SHA256`.
- Current values are placeholders I invented. Replace with real digests
  computed locally from the HF files OR add a `fetch_and_verify()` mode
  that trusts first download, pins the hash, warns on later change.
- Decision: go with "first-trust, pin on success, warn on change" — less
  maintenance and matches how TOFU keys work elsewhere.
- New file `~/Library/Application Support/Paragraphos/model_hashes.yaml`
  stores `{model_name: sha256}` per successful download.
- If a re-download produces a different hash → warn loudly in UI, keep
  the old file on disk.

### Task 1.4: feed-redirect auto-update
- File: `core/rss.py`, `ui/worker_thread.py`.
- `build_manifest()` already gets `r.url` after `follow_redirects=True`.
- Return `(canonical_url, manifest)` tuple.
- Worker thread: if `canonical_url != show.rss`, log
  "feed moved: <old> → <new>" and update `show.rss`, save
  `watchlist.yaml`.
- Test: mock 301 response, assert `watchlist.yaml` rewritten.

### Task 1.5: whisper-prompt quality feedback
- File: `core/stats.py` + new `ui/prompt_quality.py`.
- After N ≥ 5 episodes of a show complete, compute overlap between
  prompt tokens (split on `,` + whitespace) and actual transcript text.
- Low overlap (< 20%) → show a ⚠ badge on the show row with tooltip
  "whisper_prompt terms rarely appear in transcripts — consider
  updating".
- Non-blocking info, not a hard failure.

---

## Phase 1.5 — Performance (v0.5.1)

The core pipeline has three bottlenecks (measured / estimated):

| Stage | Typical time | Dominant cost |
|---|---|---|
| RSS refresh (per feed) | 0.5 – 2 s | TLS handshake + XML parse |
| MP3 download | 5 – 60 s | Network throughput |
| Whisper transcribe (60-min episode) | 180 – 300 s | Metal GPU + decoder beam |

Whisper is by far the biggest lever, so the heaviest tasks are there.

### Task 1.5.P1: whisper decoder tuning (toggle in Settings)
- File: `core/transcriber.py`, `ui/settings_pane.py`.
- Add `Settings.whisper_fast_mode` (default off). When on, pass
  `--beam-size 1 --best-of 1 -ac 0 --no-fallback` to whisper-cli.
- On M2 Pro with `large-v3-turbo`: **~2–3× speedup** at modest
  quality drop on noisy audio. Fine for most podcasts.
- Setting label: "Fast mode (less accurate)".
- Regression test asserts the flags are present only when toggle is on.

### Task 1.5.P2: persistent httpx.Client with HTTP/2 + keep-alive
- File: new `core/http.py` — a module-level `httpx.Client(http2=True,
  timeout=30, limits=httpx.Limits(max_connections=20,
  max_keepalive_connections=10))`.
- Replace ad-hoc `httpx.get` / `httpx.stream` calls in
  `rss.py`, `downloader.py`, `scrape.py`, `model_download.py`.
- Win: no TLS re-handshake between consecutive requests to the same
  host (podigee serves many feeds from a handful of IPs). Estimated
  **20–40% faster feed refresh** on the 16-show watchlist.
- Also enables the conditional-GET machinery in P5.

### Task 1.5.P3: concurrent RSS refresh
- File: `ui/worker_thread.py`.
- Today: refresh feeds serially (16 feeds × ~1 s = 16 s before first
  episode starts).
- Change: `asyncio.gather()` (or `ThreadPoolExecutor` with 8 workers) to
  fetch all feeds in parallel. Expected **~4 s for 16 feeds** (limited
  by slowest one).
- Feed backoff still applies per-feed.

### Task 1.5.P4: parallel MP3 downloads
- Covered partially by Task 2.6 (parallel download+transcribe). Spec here:
  download worker maintains a configurable pool (default 4) of
  concurrent MP3 fetches → 4× effective bandwidth for small episodes
  and hides CDN latency for big ones.
- Per-host limit: max 2 concurrent downloads from the same hostname to
  respect podcast hosts (podigee, buzzsprout etc.).

### Task 1.5.P5: RSS conditional GET (ETag / If-Modified-Since)
- Files: `core/state.py` (new `feed_etags` table or meta keys),
  `core/rss.py`.
- Persist `ETag` + `Last-Modified` per feed after each successful GET.
- Next fetch sends them as request headers; server returns 304 Not
  Modified with empty body → skip XML parse entirely.
- Win: most daily-monitor runs will get 304 on most feeds (nothing
  new), turning a 1 s/feed cost into ~100 ms/feed.

### Task 1.5.P6: SQLite WAL mode + batched writes
- File: `core/state.py`.
- `PRAGMA journal_mode=WAL` on init → concurrent readers + single
  writer without file-level locking. Watchdog + UI refresh + workers
  no longer contend.
- Batch per-episode writes (`upsert → set_status(downloading) →
  set_status(downloaded) → set_status(transcribing) →
  record_completion → set_status(done)`) into a single transaction
  where possible.

### Task 1.5.P7: library-scan mtime cache
- File: `core/library.py`.
- Today: every app start re-parses every `.md` frontmatter in
  `output_root`. Growing linearly with the vault.
- Change: persist `{path: (mtime, guid, sanitized_key)}` cache to
  `state.sqlite`. On startup, walk filesystem, skip any file whose
  mtime matches the cache; only re-parse new/changed files.
- Win: **millisecond startup** for a vault with thousands of
  transcripts, vs current ~2–5 s.

### Task 1.5.P8: whisper-cli `-p N` multi-processor file split
- File: `core/transcriber.py`.
- whisper-cli's `-p N` flag splits the input audio into N chunks and
  processes them in parallel on separate threads.
- For long episodes (≥30 min) this ~linearly scales with perf-cores.
- Needs merging: output `.srt` timestamps need re-offset — whisper-cli
  handles this internally when used correctly. Verify with A/B test.
- Expected: **2× speedup on a 4-perf-core M-series** for hour-long
  episodes. Gated behind an opt-in Settings toggle (CPU heat).

### Task 1.5.P9: stream-to-whisper (no intermediate MP3 file)
- File: `core/pipeline.py`, `core/downloader.py`, `core/transcriber.py`.
- Experimental: pipe `httpx.stream` output directly to whisper-cli's
  stdin (`-f -`). Saves one disk round-trip (~2–10 s per episode on
  slow disks, negligible on NVMe).
- Only profitable for ≥100 MB episodes. Kept opt-in (`Settings.stream_mode`).
- Breaks the MP3-retention feature — retention is irrelevant if the
  MP3 was never on disk. Document this trade-off.

### Task 1.5.P10: UI refresh throttling
- File: `ui/queue_tab.py`, `ui/main_window.py`.
- Today: QueueTab rebuilds full 500-row table every 1 s via `QTimer`.
- Change: throttle table rebuild to 3 s (header counter + status bar
  still tick every 1 s since they're cheap).
- Win: less CPU steal from the transcribe worker during long runs.

### Expected combined impact

| Change | Episode time (60-min podcast) | Notes |
|---|---|---|
| Today (large-v3-turbo, default flags) | ~240 s | Baseline |
| + P1 fast-mode toggle | ~120 s | User opt-in |
| + P8 multi-processor (4 cores) | ~60 s | With P1; long episodes only |
| + P4 parallel downloads | no per-episode change | Queue finishes sooner overall |
| + P2/P5 HTTP optimisations | feed refresh 16 s → 1–3 s | One-time per daily run |

Realistic target after Phase 1.5: **full catch-up run on the 16-show
watchlist (~3,000 pending) drops from ~200 h to ~50 h of CPU time.**

---

## Phase 2 — Throughput + core features (Tier 2, v0.6.0)

### Task 2.6: parallel download + transcribe
- File: `ui/worker_thread.py`, `core/workers.py`.
- Split into two threads: `DownloadWorker` pulls from a pending queue,
  `TranscribeWorker` pulls from a "downloaded" queue.
- I/O-bound vs CPU-bound → run concurrently for ~2× throughput.
- Respect `Settings.parallel_transcribe` for the transcribe pool size.
- State changes: `pending` → `downloading` → `downloaded` → `transcribing` → `done`
  (already in the model; just drive it from two workers).

### Task 2.9: play-preview button
- File: `ui/failed_tab.py`, `ui/show_details_dialog.py`.
- New action: "Play MP3" opens the file in the macOS default audio
  app via `open <path>`. For failed episodes the MP3 is still on disk
  (retention didn't fire). For done episodes the MP3 may have been
  deleted — re-download on demand if missing.

### Task 2.10: per-show pause
- File: `core/state.py`, `ui/shows_tab.py`, `ui/worker_thread.py`.
- `state.meta["show_paused:<slug>"]` (same pattern as backoff).
- Right-click Shows tab row → "Pause this show" / "Resume this show".
- Worker thread skips paused shows in the feed-refresh loop.
- Difference vs `enabled=False`: paused is per-session intent, enabled
  is persistent subscription state.

---

## Phase 3 — UX polish (Tier 3, v0.6.1)

### Task 3.11: search + sort in Shows/Queue tables
- Install `QSortFilterProxyModel` between each `QTableWidget` and its
  data source.
- Add a `QLineEdit` search bar above each table.
- Columns get click-to-sort via `setSortingEnabled(True)`.

### Task 3.12: re-transcribe single episode
- Right-click Queue/Shows-detail episode row → "Re-transcribe this
  episode" → status back to `pending`, priority=10, trigger check.
- Existing `.md`+`.srt` get moved to `.bak` so user can diff.

### Task 3.13: bulk-select + actions
- `ShowsTab.table.setSelectionMode(ExtendedSelection)`.
- Toolbar buttons: Disable selected · Enable selected · Mark stale ·
  Delete selected (with confirm).

### Task 3.14: daily-summary notification
- `CheckAllThread.finished_all` emits a summary `(done, failed,
  skipped)`. App posts one consolidated macOS notification after a
  catch-up run instead of one-per-episode.
- Settings toggle: `notify_mode` = per-episode / daily-summary / off.

### Task 3.15: transcript diff on re-transcribe
- On re-transcribe, the previous `.md` gets saved as `.md.bak`.
- New action "Show diff" opens both in a `QDialog` with word-level
  HTML diff (`difflib.HtmlDiff`).
- Helps tune whisper_prompt: see which proper nouns were fixed.

---

## Phase 4 — Distribution (Tier 4, v1.0 prep)

### Task 4.17: auto-update
- Use GitHub Releases as distribution channel (not Sparkle — simpler,
  no separate server).
- On startup, check `https://api.github.com/repos/<user>/paragraphos/releases/latest`
  against `CFBundleVersion`. If newer, show a non-blocking notification
  "Update available — v0.X available, you have v0.Y. Download…".
- Link opens the release page; user re-downloads manually. No
  in-place auto-upgrade (would need code signing, excluded from scope).

### Task 4.18: DMG installer
- Script (`scripts/build-dmg.sh`) wraps `hdiutil create` around the
  built `.app`. Adds a background image, `/Applications` symlink,
  positions icons.
- CI/manual: `python setup-full.py py2app && ./scripts/build-dmg.sh`.
- Output: `Paragraphos-0.5.0.dmg` in `dist/`.

### Task 4.19: universal2 build (arm64 + x86_64)
- py2app can build universal by ensuring PyQt6 + all native deps are
  present as universal wheels. Some (lxml, watchdog) may need
  `--plat-name macosx_10_13_universal2` rebuild.
- Add a `setup-full-universal.py` that sets `arch='universal2'`.
- Accept: user choice at build time.

---

## Phase 5 — Developer experience (Tier 5, v1.0)

### Task 5.20: integration test with real mini-podcast
- New fixture: `tests/integration/mini_feed.xml` + 1 short (<30 s)
  royalty-free MP3 bundled in `tests/integration/fixtures/`.
- Test drives the full pipeline (rss → download → whisper → md) end
  to end.
- Marked `@pytest.mark.integration`, not run by default. Opt-in via
  `pytest -m integration`.
- CI (Task 5.22) runs it on a schedule, not per-commit (whisper is slow).

### Task 5.21: pre-commit hook
- `.pre-commit-config.yaml` with `pytest -q`, `ruff check`, `ruff format --check`.
- `ruff` replaces flake8/black/isort — single dep, fast.
- `pre-commit install` on first clone.

### Task 5.22: CI via GitHub Actions
- `.github/workflows/test.yml`: macOS runner, Python 3.12, install deps
  from `requirements.txt` + `dev-requirements.txt`, run `pytest -q`.
- `.github/workflows/build.yml`: on tag push, `setup-full.py py2app` +
  `build-dmg.sh` + attach `.dmg` to GitHub Release.

### Task 5.23: per-module README + architecture diagram
- `core/README.md` — one paragraph per module (30 sec elevator pitch
  each).
- `ui/README.md` — same for UI components.
- `docs/architecture.md` — a mermaid diagram showing the
  ShowsTab → QueueTab → worker_thread → pipeline → (downloader |
  transcriber) → state/library flow.

---

## Execution order

Phases run in order (0 → 1 → 2 → 3 → 4 → 5) because each builds on the
previous. Within a phase, tasks are independent — they can ship in any
order as sub-commits.

Commit cadence: one commit per numbered task. Version bumps:
- v0.5.0 after Phase 1 (reliability)
- v0.6.0 after Phase 2 (new features)
- v0.6.x incrementally through Phase 3
- v1.0.0 after Phase 4 + 5 (distribution ready)

## Testing discipline

- Every task in Phase 1 gets a failing regression test FIRST (per
  `superpowers:test-driven-development`).
- Phases 2–3 get unit + smoke tests.
- Phase 4 is tested manually (DMG mount, install, launch).
- Phase 5.20 adds the integration test that would have caught the
  dotted-slug bug that cost us hours on 2026-04-20.
