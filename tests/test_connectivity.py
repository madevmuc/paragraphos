"""Tests for core/connectivity.py — probe + classifier + monitor."""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from core import connectivity
from core.connectivity import ConnectivityMonitor, is_network_error, is_online

# ---------- is_network_error ----------

_NETWORK_ERROR_HINTS = [
    "ConnectError",
    "TimeoutException",
    "NetworkError",
    "RemoteProtocolError",
    "PoolTimeout",
    "Name or service not known",
    "Could not resolve host",
    "Connection refused",
    "Connection reset",
    "No route to host",
    "Network is unreachable",
]


@pytest.mark.parametrize("hint", _NETWORK_ERROR_HINTS)
def test_is_network_error_classifies_known_hints(hint):
    """Each hint string in the classifier list must register as a network error,
    even when wrapped in a longer traceback string."""
    assert is_network_error(hint) is True
    assert is_network_error(f"some prefix: {hint} (traceback below)") is True


def test_is_network_error_handles_none_and_empty():
    assert is_network_error(None) is False
    assert is_network_error("") is False


def test_is_network_error_rejects_non_network_messages():
    # Application-level errors should NOT be classified as network failures —
    # a parse error must not get auto-requeued on reconnect.
    assert is_network_error("ValueError: invalid feed XML at line 42") is False
    assert is_network_error("KeyError: 'mp3_url'") is False
    assert is_network_error("whisper-cli failed: returncode 1") is False


# ---------- is_online ----------


class _FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_is_online_returns_true_when_probe_succeeds(monkeypatch):
    """First probe host succeeds → True. Subsequent hosts must not be tried."""
    calls: list[tuple] = []

    def fake_create(addr, timeout):
        calls.append(addr)
        return _FakeSocket()

    monkeypatch.setattr(connectivity.socket, "create_connection", fake_create)
    assert is_online(timeout=0.1) is True
    # First success wins — only the first host is probed.
    assert len(calls) == 1


def test_is_online_returns_false_when_all_probes_fail(monkeypatch):
    calls: list[tuple] = []

    def fake_create(addr, timeout):
        calls.append(addr)
        raise OSError("network unreachable")

    monkeypatch.setattr(connectivity.socket, "create_connection", fake_create)
    assert is_online(timeout=0.1) is False
    # Every probe in _PROBE_HOSTS should have been tried before giving up.
    assert len(calls) == len(connectivity._PROBE_HOSTS)


# ---------- ConnectivityMonitor signal semantics ----------


def test_monitor_emits_only_on_state_change():
    """We hand-drive the state field to verify the emit-on-flip contract
    without spinning the background thread (which would race the test)."""
    _ = QApplication.instance() or QApplication([])

    mon = ConnectivityMonitor()
    received: list[bool] = []
    mon.online_changed.connect(received.append)

    # Simulate the loop body: emit only when the new state differs from
    # the cached _last_state. Mirror the inline code in start().
    def _tick(online: bool) -> None:
        if online != mon._last_state:
            mon._last_state = online
            mon.online_changed.emit(online)

    # Initial flip from None → True fires once.
    _tick(True)
    # Steady state: no further emits.
    _tick(True)
    _tick(True)
    # Flip True → False emits once.
    _tick(False)
    _tick(False)
    # Flip False → True emits once.
    _tick(True)

    # Process queued signal deliveries before asserting (Qt may marshal
    # via the event loop on direct connect, but `received.append` is
    # synchronous Python anyway — flush defensively).
    QApplication.processEvents()
    assert received == [True, False, True]


def test_monitor_start_stop_smoke(monkeypatch):
    """Smoke: start() spawns a daemon thread that probes and stop() ends
    the loop. We patch is_online to alternate so the thread observes a
    flip without real network I/O, then assert at least one emit landed."""
    _ = QApplication.instance() or QApplication([])

    flips = iter([True, False, True, False] * 50)
    monkeypatch.setattr(connectivity, "is_online", lambda timeout=2.0: next(flips, False))

    mon = ConnectivityMonitor()
    received: list[bool] = []
    mon.online_changed.connect(received.append)

    # Patch the sleep so the loop iterates fast.
    import time as _t

    real_sleep = _t.sleep
    monkeypatch.setattr(_t, "sleep", lambda s: real_sleep(0.001))

    mon.start()
    # Give the worker a moment to flip once.
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline and not received:
        QApplication.processEvents()
        real_sleep(0.01)
    mon.stop()
    # Drain — the worker's last sleep may still finish.
    real_sleep(0.05)

    assert len(received) >= 1
