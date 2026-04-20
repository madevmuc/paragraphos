# Paragraphos Changelog

## v0.5.0 — 2026-04-20 (Phase 1 reliability)

Five reliability improvements from the ROADMAP:

- **Whisper timeout** (Task 1.1) — `subprocess.run(timeout=600)` with a
  clean `TranscriptionError` on hang. Corrupt MP3s no longer block the
  queue indefinitely.
- **Download retry with exponential backoff** (Task 1.2) — 3 attempts,
  delays 1 / 5 / 20 s, retries on 5xx / 429 / timeouts / network errors.
  Never retries 4xx (permanently gone).
- **TOFU model SHA256** (Task 1.3) — trust-on-first-use replaces the
  v0.4 placeholders that would have blocked every non-default model
  download. First download pins the hash; subsequent mismatches raise
  with clear remediation copy.
- **Feed redirect auto-update** (Task 1.4) — canonical URL after 301
  is saved to watchlist.yaml; subsequent daily checks hit the new URL
  directly.
- **Whisper prompt coverage feedback** (Task 1.5) — ⚠ tooltip on the
  title when less than 20% of prompt terms appear in the last 10
  transcripts. Non-blocking hint.

99 tests green.

## v0.4.4 — 2026-04-20 (better errors)

Every failure path now carries enough context to debug without a
reproducer. The dotted-slug bug that cost hours today would have been
obvious in seconds from this output.

- **whisper-cli non-zero exit**: error includes mp3 filename, model,
  slug, last 400 chars of stderr, last 200 chars of stdout.
- **whisper-cli exited 0 but no output files**: error lists the paths
  we expected, the actual contents of the temp dir (so mismatches jump
  out), plus stdout/stderr tails, mp3 name and slug.
- **Hallucination / silence guard**: error includes the observed word
  count, threshold, mp3 name, slug, and first 200 chars of the produced
  text (so you can tell apart silence, foreign-language misdetection,
  and whisper-loop hallucination at a glance).
- **Download failures** (pipeline): show exception type + message,
  show slug, guid, source URL, destination path.
- **Transcribe failures** (pipeline): show multi-line propagated error
  plus show/guid/mp3 path.
- **Log dock rendering**: failures now span multiple indented lines
  instead of being truncated at 100 chars — the previous truncation
  literally hid the filename that would have revealed the dot bug.
- **Root-logger errors**: download + transcribe failures are also
  logged to `~/Library/Application Support/Paragraphos/logs/` via
  `logger.error(..., exc_info=True)` so future issues leave a traceable
  trail.

## v0.4.3 — 2026-04-20 (transcriber path bug)

**Fix:** whisper-cli output lookup was using `Path.with_suffix(".txt")` on
the `-of` prefix. For slugs containing a dot mid-title — e.g.
`"… Co. (Kein) Plädoyer …"` or `"Nachhaltigkeit & Co. müssen …"` —
`with_suffix` truncates at the last dot, so we looked for `Co.txt` while
whisper-cli had actually written the full-length filename. Result: every
episode with a dot in the title raised *"whisper-cli produced no output
files"* even though whisper succeeded. Root cause reproduced with a
focused regression test; fixed by constructing the path via string
append (`stem.parent / (stem.name + ".txt")`).

Affected shows observed: 5 limmo episodes (title pattern journalistic,
heavy use of `.` as a separator). All 893 previously-transcribed
episodes were unaffected because they don't exhibit the pattern
(or were transcribed by the pre-Paragraphos `scripts/transcribe.py`).

Migration: all `failed` episodes with this error were reset to
`pending` in state.sqlite so the next Check Now will retry them.

Test coverage: new `test_transcribe_slug_with_dots_in_title` locks in
the regression; both transcriber + pipeline fakes updated to mimic
whisper-cli's actual "append suffix" behaviour.

84 tests green (83 + 1 new regression test).

## v0.4.2 — 2026-04-20 (safe quit)

- **Quit-confirmation dialog** when the queue is still running. Fires
  from tray menu "Quit", Cmd+Q, Dock → Quit — all routed through
  `quit_with_confirm()`. Default button is "Stay" to avoid accidental
  data loss. "Quit anyway" is the destructive button.
- Busy check also reads the DB directly — catches in-flight episodes
  whose status is `downloading` or `transcribing` even if the thread
  state briefly disagrees.
- `ParagraphosQApplication` now intercepts `QEvent.Quit` so ⌘Q goes
  through the confirm dialog instead of hard-killing subprocesses.

## v0.4.1 — 2026-04-20 (ETA from t=0)

- **Queue finish-time shown immediately on start**, not only after the
  first live episode completes. At `start_check()` we compute a
  historical average from the last 50 successful transcriptions in
  `state.sqlite` and use that as the ETA seed.
- Label distinguishes live vs. estimated: `ETA 1h 12m` (live rolling
  average) vs. `ETA (est.) 2h 58m` (DB-derived). Same for Queue tab's
  `avg/ep:` vs. `est/ep:`.
- New `QueueRunState.effective_avg_sec` property returns live average
  if available, historical fallback otherwise.
- `core/stats.historical_avg_transcribe_sec()` averages the wall-clock
  delta (attempted_at → completed_at) across the 50 most recent DONE
  episodes, filtering out dedup-skips (<5 s) and crashed jobs (>1 h).

## v0.4 — 2026-04-20 (hardening)

**Security — defences against malicious feeds, pages, and models.**

- `core/security.py`: central `safe_url()` (blocks `file://`, `data:`,
  `javascript:`, and private-IP hosts via SSRF-guard),
  `safe_path_within()` (traversal guard), `verify_model()` (pinned
  SHA-256 per whisper.cpp GGML model), and size caps:
  MP3 ≤ 2 GB, RSS ≤ 50 MB, HTML ≤ 10 MB.
- Downloader rejects non-audio Content-Type (refuses HTML/JSON blobs
  delivered to `<slug>.mp3`) and aborts streams exceeding the cap.
- Scraper revalidates every extracted MP3 URL against `safe_url` —
  a malicious `og:audio` pointing at `file:///…` is refused.
- OPML parser switched to `defusedxml` (blocks XXE, billion-laughs).
- Sanitizer neutralises `..` components (belt for path-traversal
  defence; `safe_path_within` is the braces).
- Pipeline verifies final `.mp3` and `.md` paths stay inside
  `output_root` before writing.
- Model downloader deletes a mismatched `.part` rather than moving it
  into place.
- About dialog gains a **Security tab** explaining the threat model,
  mitigations, residual risks, and vulnerability-reporting path.
- 20 new tests in `test_security.py`.

**Bugfix — Settings usability.**
- Settings pane wrapped in a `QScrollArea`; all 6 sections + agent
  prompt remain accessible at any window height.

## v0.3.2 — 2026-04-20 (polish 2)

- **Focus-clear on background click**: clicking on the gray background of
  any tab now removes the cursor/selection from a previously-active
  input field. Previously clicking outside a QLineEdit left it still
  looking "focused". App-level `QEvent.MouseButtonPress` filter — only
  clears focus from text/number inputs, buttons/menus behave normally.

## v0.3.1 — 2026-04-20 (polish)

- **Queue timestamps now show weekday + date** — started and expected
  finish times are rendered as `ddd, dd.mm.yyyy HH:mm` in the status
  bar and Queue tab. Uses `QLocale.system()`, so the date order
  (dd.mm vs mm.dd) matches your macOS region setting automatically.
- **Settings now organized by theme**: Library & output · Schedule &
  monitoring · Notifications · Transcription engine · Storage &
  retention · Automation & remote control.
- **AI-agent prompt template** in Settings → Automation — a ready-to-
  paste briefing for Claude Code / Gemini CLI / any agent with shell
  access. "Copy to clipboard" button included.
- **About dialog now has a Credits & Licenses tab** — full table of
  runtime dependencies with SPDX license identifiers and project
  URLs (Python, Qt/PyQt6, whisper.cpp, OpenAI Whisper model,
  APScheduler, watchdog, feedparser, httpx, pydantic, bs4, lxml,
  PyYAML, ffmpeg, Homebrew) + explanation of permissive vs. GPL
  implications and a note on podcast audio rights.

## v0.3 — 2026-04-20 (renamed)

- **Renamed to Paragraphos** (from Podtext).
  Bundle: `/Applications/Paragraphos.app`, bundle id `com.m4ma.paragraphos`,
  user data `~/Library/Application Support/Paragraphos/`.
- Automatic migration of existing state from the previous
  `~/Library/Application Support/Podtext/` and from the dev-mode
  `scripts/podcast-studio/data/` dirs — no manual data move needed.

## v0.2.4 — 2026-04-20 (late night)

- **Global queue status in status bar** — visible from every tab. Shows
  running/idle/paused, done/total counter, started-at, elapsed, ETA,
  expected finish time. Updates every second via QTimer.
- **Start / Pause / Stop buttons on both Shows and Queue tabs** (previously
  only the Shows tab had them). Queue tab's Start button turns into
  "Resume" when the queue is paused.
- **Failed tab**: new "Add failed to queue" and "Push failed on top of
  queue" buttons. The latter uses the new `episodes.priority` column —
  items with higher priority are processed first in `list_by_status`.
- **Notifications setting**: `notify_on_success` toggle now gates the
  spot-check notification too (was always firing before). New
  "Open macOS Notification settings…" button jumps straight to
  System Settings → Notifications for re-authorizing Paragraphos.
- **QueueRunState** on AppContext — shared live state so any tab can
  render the running check.

## v0.2.3 — 2026-04-20 (night)

- **Portable standalone bundle** (`setup-full.py py2app`): 310 MB `.app`
  with Python + all Python deps inside — runs on any Mac with no repo
  and no `.venv`. The first-run wizard still handles the non-Python
  system deps (Homebrew / whisper-cpp / ffmpeg / model).
- **User data moved to `~/Library/Application Support/Paragraphos/`**
  (macOS convention) — one-time lazy migration from the old
  `scripts/podcast-studio/data/` location on first launch. Watchlist is
  no longer git-tracked — per-user state.
- `scripts_legacy_shows` gracefully falls back to an empty prompts
  dict when running from a bundle on a machine without `transcribe.py`.

## v0.2.2 — 2026-04-20 (evening)

- **OPML drag-&-drop onto Dock icon** — drop an `.opml` file on
  Paragraphos in Finder or the Dock and it imports the feeds directly,
  no menu traversal needed. `Info.plist` declares Paragraphos as an
  OPML handler; `QFileOpenEvent` is intercepted and routed to the
  same import logic used by the File menu.

## v0.2.1 — 2026-04-20 (late afternoon)

- **Global library stats** on Shows tab header: transcript count,
  total audio duration (days / hours / minutes), total word count.
- **Per-show Details dialog** on row double-click: stats, episodes
  with status/words/duration, inline editor for title / RSS URL /
  language / whisper_prompt.
- **Rescan library** button: counts words in every `.md` under
  `output_root` and reads duration from sibling `.srt` files —
  one-time for historical transcripts.
- **Feed backoff wired into worker**: 3/4/5+ consecutive feed fails
  pause that feed 1/3/7 days; reset on next success.
- `state.episodes` gets `duration_sec` + `word_count` columns
  (idempotent ALTER on startup).
- Pipeline records word count + `.srt`-derived duration on completion.

## v0.2 — 2026-04-20

- **Renamed** from Podcast Studio → Paragraphos.
- **Menu bar**: full File / Edit / View / Actions / Window / Help with shortcuts.
- **⌘,** opens Settings; **⌘R** triggers Check Now; **⌘.** stops; **⌘L** toggles log dock.
- **Log dock** now timestamps every line.
- **Banner** adapts to dark/light mode.
- **Notifications** now read `done/total — Show — Episode`.
- **Settings auto-save** on every change (Save button removed).
- **Parallel workers hint** with hardware-based recommendation.
- **Terminal commands help** inline in Settings.
- **Failed tab**: added Retry all + Clear older than 30 days.
- **Queue pause/resume** (persists across app restart).
- **About + Changelog dialogs** accessible from Help menu.

## v0.1 — 2026-04-20

- Initial end-to-end build: menu-bar app, watchlist, daily monitor, curated
  episodes, library dedup (GUID + filename), umlaut-preserving sanitizer,
  MP3 retention policy, backlog filter, RSS health check, OPML import,
  spot-check notification, first-run verification against 16 real-estate
  podcast feeds (2.023 reference episodes, 0 misses).
