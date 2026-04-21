# `core/` — domain logic

Pure Python, no PyQt6 imports. Everything here must be testable without
launching a window.

| Module | One-line pitch |
|---|---|
| `rss.py` | Fetches + parses RSS feeds via feedparser; `build_manifest_with_url()` returns `(canonical_url, episodes)` so callers can persist 301 redirects. `FeedHealth.check()` probes with HEAD. |
| `downloader.py` | Streams MP3s to disk with Content-Length parity (resume-safe). 3-attempt retry on 5xx/429/timeouts (1s/5s/20s). Refuses non-audio Content-Type. |
| `transcriber.py` | Thin `subprocess.run([whisper-cli, …])` wrapper. 600s timeout. `fast_mode`/`processors` flags. Emits `<slug>.md` + `<slug>.srt`, with Obsidian frontmatter. |
| `pipeline.py` | Wires download → transcribe → save for a single episode. Owns dedup, disk-space guard, path-traversal check, stats recording, retention. |
| `state.py` | SQLite store. WAL mode. Tables: `episodes`, `jobs`, `meta`. `list_by_status()` respects priority. |
| `models.py` | Pydantic `Watchlist` + `Settings`. YAML-serialisable. |
| `library.py` | Index of existing transcripts. Scans `output_root/**/*.md` with an mtime cache for sub-second startup on large vaults. Live updates via `watchdog`. |
| `security.py` | URL allow-list (rejects `file://` / private IPs), path-traversal guard, TOFU SHA-256 for whisper models, download size caps. |
| `backoff.py` | Per-feed failure backoff (3 fails → 1d, 4 → 3d, 5+ → 7d). |
| `stats.py` | Global + per-show stats. `historical_avg_transcribe_sec()` seeds the ETA display before the first live episode. `prompt_coverage()` flags stale whisper_prompts. |
| `paths.py` | `~/Library/Application Support/Paragraphos/`. Runs one-time migration from legacy locations (knowledge-hub dev tree, older app names). |
| `deps.py` | First-run wizard checks: brew / whisper-cpp / ffmpeg / model file presence. |
| `model_download.py` | Fetches GGML models from huggingface.co, verifies via `security.verify_model()`. |
| `scrape.py` | Landing-page scraper: `og:audio` → `application/ld+json` → `<audio>` tags. Revalidates each extracted URL through `safe_url`. |
| `opml.py` | OPML subscription import. Uses `defusedxml` so a malicious OPML can't XXE. |
| `export.py` | Zip a show's `.md` + `.srt` to the export root (default `~/Downloads`). |
| `scheduler.py` | APScheduler daily cron + catch-up-on-wake detection. |
| `logger.py` | Rotating file handler → `data/logs/paragraphos.log`, 90-day retention. |
| `workers.py` | Thin `ThreadPoolExecutor` wrapper. |
| `prompt_gen.py` | Auto-generates a first-draft `whisper_prompt` from RSS metadata (frequent capitalised tokens). |
| `updater.py` | Non-blocking GitHub-release version check. Surfaces a tray notification; never auto-upgrades. |
| `http.py` | Module-level persistent `httpx.Client` (keep-alive + pool). Used by rss/downloader/scrape/model_download to share TCP connections. |
