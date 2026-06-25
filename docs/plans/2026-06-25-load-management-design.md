# Lastmanagement — Hintergrundlast-Stufen — Design

**Datum:** 2026-06-25
**Status:** Approved, ready for implementation plan

## Problem

Transkription ist der ressourcenintensive Teil. Jede Episode startet einen
`whisper-cli`-Subprozess (Homebrew whisper.cpp) mit fest verdrahtet
`-t 6` Threads. `parallel_transcribe` (N gleichzeitige Episoden) ×
`whisper_multiproc` (`-p` Audio-Split innerhalb eines Prozesses) lasten die
CPU bis zu `N × split` Kerne voll aus. Auf einem M2 Pro (8 P-Kerne) pegt
das alle Performance-Kerne und macht den Rechner spürbar träge — paragraphos
läuft dann nicht mehr unbemerkt im Hintergrund, sondern stört die normale
Arbeit.

Ziel: in den Einstellungen einstellbar machen, **wie sehr** paragraphos den
Rechner auslasten darf, so dass der Rechner immer responsive bleibt, aber
paragraphos die gerade ungenutzten Ressourcen sinnvoll nutzt.

## Gewählter Ansatz (aus Brainstorming)

**Adaptiv, OS-gesteuert** (nicht Aktivitäts-Polling, nicht nur fester
Deckel): paragraphos läuft als Hintergrund-Priorität über macOS-native
Mechanismen (`nice` / `taskpolicy -b`). Das System gibt ihm automatisch nur
freie CPU und weicht sofort zurück, sobald der Nutzer aktiv arbeitet — ohne
dass paragraphos selbst das Nutzerverhalten überwacht. Der Nutzer setzt nur
eine Obergrenze über **3 benannte Stufen**.

**Mechanismus-Variante B (Core-Budget + QoS):** Jede Stufe bildet *sowohl*
ein CPU-Kern-Budget (→ leitet `parallel_transcribe` und `-t`-Threads aus
`core/hw.py` ab) *als auch* eine Scheduling-Stufe ab. Das OS erledigt das
sekündliche Ausweichen (via `nice`); das Budget setzt die Obergrenze.

**GPU bleibt unangetastet.** whisper.cpp lagert die schwere Mathematik auf
Metal (GPU) aus; macOS gibt dem WindowServer GPU-Priorität, daher macht
GPU-Offload die UI selten ruckelig, und die GPU ist auf Apple Silicon
energieeffizient. Die gefühlte Trägheit kommt von der CPU-Sättigung — **CPU
ist der Hebel.**

## Stufe → Ressourcen-Mapping (Kern)

Stufen verdrahten keine festen Zahlen, sondern leiten aus `core/hw.py` ab
(Gesamt-/Performance-Kerne), damit sie auf jedem Mac skalieren. Aufgelöst
für ein 8P/4E-Gerät (M2 Pro):

| Stufe | CPU-Budget | `parallel` | `-t` Threads | Scheduling | Gefühl |
|-------|-----------|-----------|-------------|-----------|--------|
| **Leise** (`quiet`) | ~2 Threads, E-Kerne | 1 | 2 | `taskpolicy -b` (Apple Background-Tier) | Unsichtbar; langsam, aber nie spürbar |
| **Ausgewogen** (`balanced`) | ~halbe P-Kerne | 1 | 4 | `nice -n 10` | Nutzt freie Kapazität, weicht beim Arbeiten sofort |
| **Volle Leistung** (`full`) | ~alle P-Kerne | 2 | 4 | `nice -n 5` *(Checkbox an)* / normal *(aus)* | Max. Durchsatz, dennoch höflich, sofern nicht abgewählt |

`whisper_multiproc` bleibt in allen Stufen 1 (multipliziert Kerne weiter mit
abnehmendem Ertrag — kontraproduktiv für einen *lastgesteuerten* Modus).

Die Ableitung lebt in **einer reinen Funktion**, damit trivial unit-testbar:

```python
# core/load.py
from dataclasses import dataclass
from typing import Literal

LoadLevel = Literal["quiet", "balanced", "full"]
Qos = Literal["background", "nice", "normal"]

@dataclass(frozen=True)
class LoadProfile:
    parallel: int      # Anzahl gleichzeitiger Transkriptions-Worker
    threads: int       # whisper-cli -t
    qos: Qos           # Scheduling-Tier → Kommando-Prefix
    nice_level: int    # nur relevant wenn qos == "nice"

def resolve_load_profile(
    level: LoadLevel, hw, *, background_priority: bool
) -> LoadProfile:
    """Pure: (Stufe, HW, Checkbox) → konkrete Lauf-Parameter.

    Skaliert über hw.perf_cores (Fallback hw.logical_cores auf Intel).
    """
    ...
```

Tier → Kommando-Prefix (siehe Mechanismus): `background` → `["taskpolicy",
"-b"]`, `nice` → `["nice", "-n", str(nice_level)]`, `normal` → `[]`.

## Mechanismus — wie das Tier angewandt wird

`core/transcriber.py` baut das whisper-cli-Kommando heute mit fest
verdrahtetem `THREADS = "6"`. Zwei Änderungen:

1. `-t` wird zur `threads` des Profils (durchgereicht über
   `transcribe_phase`).
2. Das Kommando bekommt einen **Prefix** je Tier: `["taskpolicy", "-b",
   *cmd]`, `["nice", "-n", "10", *cmd]` oder kein Prefix. **Argv-Prefix
   statt `preexec_fn=os.nice`** ist die thread-sichere Wahl — es laufen
   mehrere `_TranscribeWorker`-QThreads, und `preexec_fn` ist mit Threads
   nicht sicher.

`parallel_transcribe` steuert bereits die Worker-Anzahl in
`worker_thread.py` (~Z. 732); wir füttern es mit dem aufgelösten Wert.

`taskpolicy` und `nice` sind macOS-Standardtools (beide vorhanden geprüft) —
**keine neuen Abhängigkeiten.**

## Settings-Modell (`core/models.py`)

- **Neu:** `load_level: Literal["quiet", "balanced", "full"] = "balanced"`
  und `background_priority: bool = True`.
- **Entfernt** als Nutzerfelder: `parallel_transcribe`, `whisper_multiproc`
  — jetzt aus der Stufe *berechnet*. Laufzeit-Code liest sie nicht mehr
  direkt, sondern ruft `resolve_load_profile(...)`.
- **Migration** bestehender Nutzer: beim Laden, falls `load_level` fehlt,
  aber ein Legacy-`parallel_transcribe` existiert, Stufe ableiten
  (`≥2 → "full"`, sonst `"balanced"`), damit sich kein Setup still ändert.
  Unbekannte Legacy-Schlüssel werden sonst ignoriert.
- **Default-Seeding:** Neuinstallationen bekommen `"balanced"` (der
  responsive Default), ersetzt das heutige HW-Seeding von
  `parallel_transcribe`. Große Maschinen können auf „Volle Leistung" hoch.

## UI (`ui/settings_pane.py`)

Die „Parallel workers"- / multiproc-Spinboxen werden ersetzt durch **eine
Gruppe „Hintergrundlast"**:

- 3 Radio-Buttons: Leise / Ausgewogen / Volle Leistung.
- Checkbox „Mit Hintergrund-Priorität laufen" (Default an).
- Live-Anzeige-Label, das spiegelt was die Stufe tut: z. B. „Diese Stufe:
  1 Episode × 4 Threads, weicht aktiver Nutzung aus."

**Stufe ist autoritativ (v1):** keine manuelle Übersteuerung der
abgeleiteten Zahlen. Die alten Spinboxen verschwinden; eine
Feintuning-Option kann später folgen.

Persistenz: `_do_save()` schreibt `load_level` + `background_priority`
(bestehendes Debounce-Muster).

Der HW-Divergenz-„tuning hint"-Banner in `queue_tab.py` wird **entfernt** —
er verglich gegen `parallel_transcribe`, das als Knopf nicht mehr existiert
(inkl. der zugehörigen `_refresh_tuning_hint`-Logik + des `_tuning_hint`-
Labels).

## Datenfluss & Wirkungszeitpunkt

`settings.yaml → ctx.settings → worker_thread` löst das Profil bei Lauf-Start
und je Worker-Spawn auf → `transcriber` baut argv mit QoS-Prefix +
`-t threads`. Änderungen wirken auf **neu gestartete** Transkriptionen; eine
laufende whisper-Instanz behält ihre Start-Parameter (kein Mid-Flight-Renice
— YAGNI). Stufenwechsel greift ab der nächsten Episode.

## Tests

- `tests/test_load_profile.py` — `resolve_load_profile` über jede
  Kombination `level × background_priority`, auf gemockter HW (8P/4E;
  kleine 4-Kern-Maschine; Intel-Box ohne perf-level-Split) → prüft
  `(parallel, threads, qos, nice_level)`.
- Kommando-Konstruktion — `transcriber`-argv trägt den richtigen Prefix
  (`taskpolicy -b` / `nice -n N` / keiner) + `-t N` (bestehende
  transcriber-Tests erweitern).
- Settings-Roundtrip + Legacy→Stufe-Migration (alt `parallel_transcribe`
  bildet Stufe; unbekannte Felder ignoriert).
- Default-Seed = `balanced`.

## YAGNI / bewusste Entscheidungen

- **Kein** Aktivitäts-/Idle-Polling — das OS erledigt das Ausweichen.
- **Keine** Akku-/Thermal-Umschaltung in v1 (mögliche spätere Erweiterung).
- **Kein** GPU-Throttling / `--no-gpu` — Metal bleibt an.
- **Kein** hartes CPU-%-Duty-Cycling (SIGSTOP/SIGCONT) — bekämpft den
  Scheduler, unnötig neben `nice` + Budget.
- **Kein** Mid-Run-Renice laufender whisper-Prozesse.
- **Keine** manuelle Pro-Stufe-Übersteuerung (zurückgestellt).
- `whisper_multiproc` in allen Stufen = 1.
