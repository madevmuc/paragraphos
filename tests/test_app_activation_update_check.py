"""Headless smoke of the on-activation update re-check slot.

Drives the real ``ParagraphosApp._on_activation_update_check`` against a
minimal stand-in self plus a real ``StateStore``, with ``check_for_update``
monkeypatched to a recorder so no network/thread is spawned. The real GUI
wiring (applicationStateChanged firing on macOS) stays manual.
"""

from __future__ import annotations

import types
from datetime import datetime, timedelta, timezone

import pytest
from PyQt6.QtCore import Qt

import app as app_module
from core.models import Settings
from core.state import StateStore

ACTIVE = Qt.ApplicationState.ApplicationActive
INACTIVE = Qt.ApplicationState.ApplicationInactive


class _FakeApp:
    """Carries exactly the attributes ``_on_activation_update_check`` touches."""

    def __init__(self, state: StateStore, settings: Settings):
        self.ctx = types.SimpleNamespace(state=state, settings=settings)
        self.update_available = types.SimpleNamespace(emit=lambda *a: None)


@pytest.fixture()
def state(tmp_path) -> StateStore:
    s = StateStore(tmp_path / "state.sqlite")
    s.init_schema()
    return s


@pytest.fixture()
def recorder(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        "core.updater.check_for_update",
        lambda **kw: calls.append(kw),
    )
    return calls


def _activate(fake, st=ACTIVE):
    app_module.ParagraphosApp._on_activation_update_check(fake, st)


def test_checks_when_due_and_records_timestamp(state, recorder):
    fake = _FakeApp(state, Settings())  # update_check_enabled True by default
    before = datetime.now(timezone.utc)

    _activate(fake)

    assert len(recorder) == 1
    call = recorder[0]
    assert call["repo"] == fake.ctx.settings.github_repo
    assert callable(call["on_update_available"])
    written = state.get_meta("last_update_check")
    assert written is not None
    # set-meta-before-fire: timestamp is fresh (written this call, UTC iso)
    assert (datetime.fromisoformat(written) - before) < timedelta(seconds=5)


def test_gated_within_24h(state, recorder):
    recent = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    state.set_meta("last_update_check", recent)
    fake = _FakeApp(state, Settings())

    _activate(fake)

    assert recorder == []


def test_disabled_by_setting(state, recorder):
    fake = _FakeApp(state, Settings(update_check_enabled=False))

    _activate(fake)

    assert recorder == []
    assert state.get_meta("last_update_check") is None


def test_ignores_non_active_state(state, recorder):
    fake = _FakeApp(state, Settings())

    _activate(fake, INACTIVE)

    assert recorder == []
    assert state.get_meta("last_update_check") is None


def test_rechecks_after_24h(state, recorder):
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    state.set_meta("last_update_check", old)
    fake = _FakeApp(state, Settings())

    _activate(fake)

    assert len(recorder) == 1
    assert state.get_meta("last_update_check") != old
