# Offline handling + resizable columns — Design

**Date:** 2026-04-23
**Status:** Brainstorm approved.
**Target:** ship together as a single follow-up to v2.0 work.

Two small independent features.

---

## Feature 1 — Offline detect, pause, auto-resume

### Goal

When the network is down, paragraphos pauses the queue + shows a banner instead of accumulating "failed" rows. When the network is back, the queue resumes automatically and any items that failed with a **network-class** error in the last N hours get re-queued so the user wakes up to a clean state after laptop sleep / VPN flap / coffee-shop wifi.

### Architecture

A small `core/connectivity.py` module:

- `is_online(timeout=2.0) -> bool` — non-blocking TCP probe to `1.1.1.1:443` (Cloudflare) with a httpx-style fallback to `8.8.8.8:443` (Google DNS) and `youtube.com:443`. First success wins. No DNS used (raw IP), so a broken resolver still gives the right answer.
- `ConnectivityMonitor(QObject)` — thread that probes every 30 s when online, every 5 s when offline. Emits `online_changed(bool)` on flip.

Wiring in `app.py`:

- Start the monitor at app launch.
- On `online_changed(False)`:
  - Set `state.set_meta("queue_paused", "1")` and remember the cause via `state.set_meta("paused_reason", "offline")`.
  - Show a non-blocking top-of-window banner "Offline — queue paused, will resume when connection returns."
- On `online_changed(True)`:
  - If `paused_reason == "offline"`, clear `queue_paused` + `paused_reason`.
  - Re-queue: `UPDATE episodes SET status='pending', error_text=NULL WHERE status='failed' AND <error_text matches network classifier> AND <attempted_at within last 24 h>`.
  - Trigger `start_check(force=True)` to drain immediately.
  - Hide banner.

The user-initiated pause (Queue tab Pause button) sets `paused_reason="user"` so the auto-resume path won't override it.

### Network-error classifier

A small helper `core.connectivity.is_network_error(error_text: str) -> bool`:

```python
_NET_HINTS = (
    "ConnectError", "TimeoutException", "NetworkError",
    "RemoteProtocolError", "PoolTimeout",
    "Name or service not known", "Could not resolve host",
    "Connection refused", "Connection reset",
    "No route to host",
)
return any(h in (error_text or "") for h in _NET_HINTS)
```

This matches httpx's exception names already used by `core/downloader.py:47` plus the common OS-level strings. **Conservative on purpose**: a syntax error in a feed shouldn't get re-queued just because we came back online.

### Banner

Reuses the existing `MainWindow.banner` slot (already used for the wiki-compile + update banners). Just adds a third state `"offline"`. Auto-dismissed when reconnect happens.

### Settings

- `connectivity_monitor_enabled: bool = True` (off-switch; some users behind captive portals may not want noisy probes).
- `auto_resume_failed_window_hours: int = 24` (how far back to re-queue network-failed items).

Both surfaced under Settings → Schedule & monitoring.

### Out of scope

- Mobile-style data-cap awareness.
- Offline-first download (caching feeds for later parse). The app is fundamentally pull-based — nothing to do without network.
- Per-host connectivity (e.g., one CDN flapping while DNS is fine). The single TCP probe is good enough; per-host failures still flow through the existing per-feed backoff.

### Testing

- Unit: `is_network_error` with a parametrised list of error strings.
- Unit: `ConnectivityMonitor` with a fake probe (mock `socket`).
- Smoke: monkeypatch `is_online` to return False → assert `queue_paused=1` set within 5 s.

---

## Feature 2 — Resizable columns + reset

### Goal

User can drag column borders in Shows / Queue / Failed tables. Widths persist across restarts. Right-click on the header → "Reset columns" returns to defaults.

### Architecture

A tiny `ui/widgets/resizable_header.py`:

```python
def make_resizable(table: QTableView, *, settings_key: str,
                   stretch_col: int | None = None,
                   defaults: dict[int, int] | None = None) -> None:
    """Configure table columns for user-resize + persistence.

    - All columns: ResizeMode.Interactive, except `stretch_col` which
      stays Stretch so it fills remaining space.
    - On construction: load widths from QSettings under `settings_key`;
      fall back to `defaults` mapping (col → px) when no saved value.
    - On user drag (sectionResized signal): debounce-save to QSettings.
    - Right-click header → context menu with 'Reset columns' →
      restores `defaults` and clears the QSettings entry.
    """
```

Call sites — one line each in `shows_tab.py`, `queue_tab.py`, `failed_tab.py`:

```python
from ui.widgets.resizable_header import make_resizable
make_resizable(self.table,
               settings_key="shows/columns",
               stretch_col=1,                       # title fills space
               defaults={0: 60, 2: 80, 3: 80, 4: 90})
```

### Persistence

`QSettings` (we already use it elsewhere for window geometry). Key per table:

- `shows/columns` → `{"0": 60, "2": 80, ...}`
- `queue/columns`
- `failed/columns`

Stored as JSON string for forward-compat (Qt's QVariant on dict varies across platforms).

### Status column on Queue (a special case)

Currently `Fixed` at 150 px because `transcribing · XXX%` updates every second and any auto-fit would cascade a layout twitch. Keep it as Fixed — but expose width in defaults so user reset still works. We just don't make it Interactive (no benefit; Fixed reflects that the live-text width is determined by content, not user pref).

Decision: convert all currently-`ResizeToContents` columns to `Interactive`. Keep currently-`Stretch` columns as `Stretch`. Keep currently-`Fixed` columns as `Fixed`.

### Out of scope

- Column reorder (drag a header sideways). Pure resize is the ask.
- Hide/show columns. Same — not asked.

### Testing

- Unit: `make_resizable` with a mock QSettings — saves on resize signal, restores on init.
- Smoke: construct each tab, drag a header section, restart-equivalent, verify width restored.

---

## Phasing

Two independent commits (file-disjoint; can ship in either order):

1. **Connectivity monitor + banner + auto-resume** — `core/connectivity.py` (new), `app.py` wiring, `ui/main_window.py` banner state, settings additions.
2. **Resizable columns** — `ui/widgets/resizable_header.py` (new), one-line call site per table.

Both behind no flag; user-visible behaviour change. Tests added with each.
