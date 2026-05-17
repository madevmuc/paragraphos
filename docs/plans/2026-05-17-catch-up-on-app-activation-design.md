# Catch-up bei App-Aktivierung — Design

**Datum:** 2026-05-17
**Status:** Approved, ready for implementation plan

## Problem

Der tägliche Check (`daily_check_time`, Default 0900) wird verpasst, wenn um
diese Uhrzeit der Mac aus war, die App busy war oder der Check inhaltlich
scheiterte (kein Netz). Aktuell holt nur der **App-Start** einen verpassten
Check nach (`app.py:348`, via `should_catch_up`). Läuft die App im Tray
weiter, gibt es bis zum nächsten echten Neustart kein erneutes Trigger —
selbst wenn der User die App wieder in den Vordergrund holt.

Zusätzlich setzt `_on_check_done` (`app.py:585`) `last_successful_check`
**immer** wenn ein Check durchläuft, auch bei einem inhaltlichen Fehlschlag
(kein Netz). Damit gilt ein gescheiterter Check fälschlich als erledigt und
wird nie nachgeholt.

## Ziel

Sobald die App das nächste Mal in den Vordergrund genommen wird
(App-Aktivierung), einen verpassten Check automatisch nachholen — sofern
`catch_up_missed` an ist, gerade kein Check läuft und der heutige Slot noch
nicht erfolgreich erledigt wurde.

## Gewählter Ansatz

**A — Activation-Hook + Erfolgs-Gate.** Minimal-invasiv, nutzt die
vorhandene `should_catch_up`-Maschinerie, kein neues State-Feld.

Verworfen:
- **B (eigenes `pending_catch_up`-Flag):** mehr State, Crash-Edge-Cases
  zwischen Set und Clear.
- **C (periodischer Timer):** feuert auch ohne dass jemand die App
  ansieht — widerspricht dem ausdrücklichen Wunsch „sobald im Vordergrund".

## Komponente 1 — Erfolgs-Gate in `_on_check_done` (app.py:585)

`last_successful_check` wird **nur** gesetzt, wenn der Check echt
erfolgreich war. Nicht setzen, wenn eine dieser Bedingungen zutrifft:

- `self._thread._stop` true — User-Abbruch oder Offline-Pause
- `queue_paused == "1"` — Lauf endete sofort weil pausiert
  (worker_thread.py:545–548)
- `not is_online()` — kein Netz, der Lauf konnte nichts Sinnvolles tun

Sonst → `last_successful_check = now` (wie bisher). Einzelne Feed-Fehler
zählen weiter als Erfolg (eigener 1/3/7-Tage-Backoff schützt — sonst würde
ein einziger kaputter Feed ewige Catch-up-Loops auslösen).

Die reine Entscheidung wird als Qt-freie Funktion extrahiert, damit sie
ohne GUI testbar ist:

```python
# core/scheduler.py
def check_counts_as_success(*, stopped: bool, paused: bool, online: bool) -> bool:
    return not stopped and not paused and online
```

`is_online()` ist ein ~2 s Blocking-Call auf dem GUI-Thread, läuft aber
nur einmal pro Check-Ende — akzeptabel.

## Komponente 2 — Activation-Hook (app.py `__init__`, nach Scheduler-Setup)

```python
QApplication.instance().applicationStateChanged.connect(self._on_app_activated)

def _on_app_activated(self, state):
    if state != Qt.ApplicationState.ApplicationActive:
        return
    if not self.ctx.settings.catch_up_missed:
        return
    if self._is_queue_busy():            # nicht in laufenden Lauf reinpfuschen
        return
    if not should_catch_up(
        self.ctx.state.get_meta("last_successful_check"),
        self.ctx.settings.daily_check_time,
    ):
        return
    self.ctx.state.set_meta("queue_paused", "0")
    QTimer.singleShot(_delay_ms, self._run_check)   # gleiche Delay-Logik wie Launch
```

`should_catch_up` gated bereits auf „einmal pro Slot" (Vergleich gegen
`last_successful_check`), also kein Re-Trigger bei jedem Tray-Klick am
selben Tag. `_is_queue_busy()` existiert bereits (`app.py:573`).
`_delay_ms` wird wie beim Launch-Pfad aus `auto_start_delay_seconds`
berechnet.

## Szenarien-Abdeckung

| Szenario | Verhalten |
|---|---|
| Mac aus um 0900 | App-Start-Catch-up (unverändert) ODER erste Aktivierung holt nach |
| App busy um 0900 | Cron-`_run_check` bailt, `last_successful_check` bleibt alt → nächste Aktivierung holt nach |
| Check offline gescheitert um 0900 | Erfolgs-Gate setzt Timestamp nicht → nächste Aktivierung holt nach |
| Normaler erfolgreicher 0900-Check | Gate setzt Timestamp → `should_catch_up` false → keine Doppel-Läufe |

## Tests

- `should_catch_up` ist bereits unit-getestet — unverändert.
- Neu: Unit-Test für `check_counts_as_success` (gestoppt/paused/offline →
  False; sonst True).
- Activation-Hook-Guard: schwer headless zu testen (Qt-Signal). Die reinen
  Guards (`should_catch_up`, `check_counts_as_success`, `_is_queue_busy`)
  sind einzeln testbar; der Hook selbst per manuellem Smoke-Test.

## Edge-Cases / bewusste Entscheidungen

- **Keine Mac-Wake-Erkennung** — bewusst nur „im Vordergrund", kein
  Hintergrund-Autostart.
- **Erfolg = grob connectivity-basiert**, nicht feed-granular — der
  vorhandene Feed-Backoff übernimmt das Feine.
- `applicationStateChanged` feuert auch beim allerersten Aktivieren direkt
  nach Launch → kann mit dem Launch-Catch-up zusammenfallen.
  `_is_queue_busy()` + `should_catch_up` verhindern den Doppellauf.
