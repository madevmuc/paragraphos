# Periodischer Update-Check bei App-Aktivierung — Design

**Datum:** 2026-05-17
**Status:** Approved, ready for implementation plan

## Problem

`core/updater.py` `check_for_update()` läuft **nur einmal beim App-Start**
(`app.py:276`). Es gibt keinen periodischen Re-Check. Paragraphos ist aber
eine Tray-App, die dauerhaft läuft (dasselbe Long-running-Modell, für das
gerade das Daily-Check-Catch-up gebaut wurde). Ein Nutzer, der die App
selten beendet, läuft potenziell wochenlang auf einer veralteten Version
ohne je benachrichtigt zu werden — eine veröffentlichte Release wird erst
beim nächsten echten Neustart bemerkt.

Zusätzlich feuert `_on_update_available` (`app.py:399`) die Tray-Notification
**bei jedem Start** erneut, solange ein Update aussteht — unnötiges Nerven.

## Ziel

Beim Vordergrund-Holen der App (App-Aktivierung) zusätzlich auf Updates
prüfen, gegated auf max. 1×/24 h, abschaltbar per Setting, mit
Tray-Notification genau 1× pro neuer Version.

## Gewählte Entscheidungen (aus Brainstorming)

- **Trigger:** App-Activation-Hook (nicht Scheduler, nicht eigener Timer).
- **Re-Notify:** Tray-Notification 1× pro Versions-Tag; Banner bleibt
  persistente leise Erinnerung (hat schon Dismiss-pro-Tag-Logik).
- **Opt-out:** ein Setting `update_check_enabled` (Default an), das
  Startup-Check **und** Activation-Re-Check steuert.
- **Integrationsform:** separater, entkoppelter Slot (Ansatz A) — nicht
  inline in `_on_app_activated`, damit der Update-Check nicht an den
  Catch-up-Guards hängt und das gerade fertige Feature unangetastet bleibt.

## Komponente 1 — Opt-out-Setting

`core/models.py` `Settings`: `update_check_enabled: bool = True`. Gated
beide Pfade. `ui/settings_pane.py`: Checkbox analog zur vorhandenen
`self.catchup`-Checkbox (gleiches `_schedule_save`-Muster, gleicher
Save-Block in `_save`). Aus → kein GitHub-Hit (respektiert „no telemetry").

## Komponente 2 — Qt-freier Re-Check-Gate-Helper

In `core/updater.py`:

```python
def should_recheck_update(
    last_iso: Optional[str], now: datetime, min_interval_h: float = 24.0
) -> bool:
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(last_iso)
    except ValueError:
        return True
    return (now - last) >= timedelta(hours=min_interval_h)
```

Rein, ohne Qt/Netz, unit-testbar (wie `check_counts_as_success`). 24 h
Mindestintervall statt Kalendertag → robust gegen Tagesgrenzen/Zeitzonen.
Ungültiges ISO → defensiv `True` (lieber einmal zu viel prüfen).

## Komponente 3 — Separater Activation-Slot (Ansatz A)

Neue Methode `_on_activation_update_check(self, state: Qt.ApplicationState)`,
in `__init__` **zusätzlich** an `applicationStateChanged` connectet (eigener
Slot, entkoppelt von `_on_app_activated`):

```python
def _on_activation_update_check(self, state: Qt.ApplicationState) -> None:
    if state != Qt.ApplicationState.ApplicationActive:
        return
    if not self.ctx.settings.update_check_enabled:
        return
    now = datetime.now(timezone.utc)
    if not should_recheck_update(
        self.ctx.state.get_meta("last_update_check"), now
    ):
        return
    self.ctx.state.set_meta("last_update_check", now.isoformat())
    check_for_update(
        local_version=_LOCAL_VERSION,
        on_update_available=lambda t, u: self.update_available.emit(t, u),
        repo=self.ctx.settings.github_repo,
    )
```

`check_for_update` spawnt selbst einen Daemon-Thread → kein GUI-Freeze.
Timestamp wird bei *Initiierung* gesetzt (nicht bei Erfolg, da
`check_for_update` keinen Erfolgs-Callback hat — nur „Update da"-Callback);
ein transienter Offline-Moment überspringt diesen 24 h-Slot, Startup-Check +
Folgetage decken das ab. Bewusste YAGNI-Entscheidung: kein Callback-Umbau
von `check_for_update`.

## Komponente 4 — Tray-Notification-Dedupe (1×/Version)

`_on_update_available` (`app.py:399`): vor `tray.showMessage` ein
QSettings-Gate, ausgelagert als reine Funktion für Testbarkeit:

```python
# core/updater.py
def should_notify_tag(notified_tag: str, tag: str) -> bool:
    return notified_tag != tag
```

```python
# app.py _on_update_available
s = QSettings("madevmuc", "Paragraphos")
if should_notify_tag(s.value("updater/notified_tag", "", type=str), tag):
    self.tray.showMessage(...)
    s.setValue("updater/notified_tag", tag)
```

Banner (`show_update_banner`) wird wie bisher **immer** aufgefrischt.
Effekt: Tray-Notification genau 1× pro neuem Tag — egal ob Startup oder
Re-Check, egal wie oft neu gestartet. Behebt das bestehende
„jeder Launch re-nervt".

## Startup-Check-Gating

`app.py:276`: bestehender `check_for_update`-Aufruf in
`if self.ctx.settings.update_check_enabled:` einwickeln. Sonst unverändert.

## Fehlerverhalten

Unverändert still (wie heute) — `check_for_update` schluckt Netzwerk-/
API-Fehler, kein Retry. Akzeptabel für unkritische Notifications;
Startup + tägliche Aktivierungen geben genug Versuche.

## Tests

- `should_recheck_update`: Unit-Tests (None→True; <24 h→False; ≥24 h→True;
  ungültiges ISO→True).
- `should_notify_tag`: Unit-Tests (gleicher Tag→False; anderer/leerer
  Tag→True).
- `_on_activation_update_check`: headless-Smoke analog zum bestehenden
  `tests/test_app_activation_catchup.py` (Fake-self, gemocktes
  `check_for_update`, echtes StateStore) — Szenarien: enabled/disabled,
  <24 h gegated, state≠Active, Timestamp gesetzt, check_for_update
  aufgerufen.
- Bestehende `tests/test_updater.py` (5) bleiben grün.

## Bewusste Entscheidungen / YAGNI

- Kein eigener Timer, kein Scheduler-Andocken (Activation-Hook gewählt).
- Kein Erfolgs-Callback-Umbau von `check_for_update`.
- Läuft nicht wenn die App ungenutzt im Tray hängt — akzeptierter
  Trade-off der Activation-Wahl (Startup-Check fängt den „lange zu, dann
  neu gestartet"-Fall).
- Re-Check-Slot ist entkoppelt vom Catch-up-Slot — `_on_app_activated`
  und sein `_catch_up_pending`-Latch werden nicht angefasst.
- **Benigne Doppelprüfung Launch → erste Aktivierung:** Der Startup-Check
  schreibt `last_update_check` bewusst NICHT (kein Erfolgs-Callback). Die
  erste `ApplicationActive`-Aktivierung nach dem Launch sieht daher kein/
  veraltetes Meta und feuert eine zweite `releases/latest`-Anfrage wenige
  Sekunden nach der Startup-Anfrage. Akzeptiert: zwei unauth. GitHub-GETs
  (weit unter 60/h), Tray-Dedupe verhindert den Doppel-Toast. **Nicht
  „fixen" durch Kopplung des Startup-Pfads an `last_update_check`** — das
  würde den absichtlich vermiedenen „offline beim Start überspringt den
  24 h-Slot"-Fall wieder einführen.
