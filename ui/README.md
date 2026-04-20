# `ui/` — PyQt6 widgets

All visible surface. Avoid touching `core/` — widgets should bind to
state and signals, not contain business logic.

| Module | Role |
|---|---|
| `main_window.py` | Top-level `QMainWindow`. Tabs (to be replaced by a sidebar in Phase 6). Status bar with live queue ETA. Global shortcuts (⌘, ⌘R ⌘. ⌘L). |
| `shows_tab.py` | Table of shows. Search filter. Right-click context menu (check / mark stale / toggle enabled / pause). Global library stats header + ⚠ badge for low-prompt-coverage shows. |
| `queue_tab.py` | Pending/in-flight episode table. Live stats header with started / elapsed / avg/est per episode / ETA / finish time with day-of-week. Start/Pause/Stop buttons. |
| `failed_tab.py` | Failed-episode table with retry / retry-all / push-on-top / play-MP3 / clear-older-than-30d actions. |
| `settings_pane.py` | Sectioned form (Library · Schedule · Notifications · Engine · Storage · Automation). Auto-saves with a 250ms debounce. Terminal-commands help + copyable AI-agent prompt. |
| `first_run_wizard.py` | Modal dep-check on first launch: Homebrew / whisper-cpp / ffmpeg / model. |
| `add_show_dialog.py` | Add-podcast flow: iTunes name search or RSS URL. Auto-generates a whisper_prompt. Backlog policy picker. |
| `add_episodes_dialog.py` | Curated per-episode add (paste URLs). |
| `show_details_dialog.py` | Per-show stats + settings + recent episodes. Opens on row double-click. |
| `about_dialog.py` | About + Credits & Licenses + Security tabs. |
| `menu_bar.py` | Full native macOS menu bar (File / Edit / View / Actions / Window / Help) with standard shortcuts. |
| `app_context.py` | `AppContext` dataclass: shared state, settings, watchlist, library index, `QueueRunState` (live progress). Carries the `watchdog` observer. |
| `worker_thread.py` | `CheckAllThread(QThread)`. Owns the main pipeline loop. Emits `queue_sized`, `progress`, `episode_done`, `finished_all` signals. |
| `log_dock.py` | Timestamped live log widget anchored at the bottom of the window. |
