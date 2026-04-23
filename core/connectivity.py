"""Network connectivity detection + classifier + background monitor.

Used by app.py to pause the queue when the laptop drops offline (sleep,
VPN flap, coffee-shop wifi) and to auto-resume + re-queue network-failed
items when the network returns. See
``docs/plans/2026-04-23-offline-and-resizable-columns-design.md``.

Why raw IPs first? On the broken-resolver case (corporate VPN flap) DNS
times out long before the TCP probe would, so the user sees "offline"
even though the route is fine. Probing 1.1.1.1 directly bypasses that.
"""

from __future__ import annotations

import socket
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal

# Hosts to probe in order. Raw IPs first so a broken DNS resolver
# (common after VPN flap) still returns the correct online status; the
# hostname-based fallback covers the captive-portal case where TCP to
# 443 on raw IPs is filtered but the user-controlled gateway resolves.
_PROBE_HOSTS: tuple[tuple[str, int], ...] = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 443),
    ("youtube.com", 443),
)


def is_online(timeout: float = 2.0) -> bool:
    """TCP-connect probe to a small fixed list of hosts. First success wins.

    Uses raw IPs first to bypass broken DNS. Returns False only when every
    probe in ``_PROBE_HOSTS`` fails — conservative on purpose, so a single
    flaky CDN doesn't trigger a queue pause.
    """
    for host, port in _PROBE_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


# Substring hints that mark an error as "network class". Matches httpx
# exception names already used by core/downloader.py plus the common
# OS-level strings whisper-cli + yt-dlp surface. Conservative on
# purpose: a feed parse error or whisper crash MUST NOT requeue when
# the network returns — those need user attention.
_NET_HINTS: tuple[str, ...] = (
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
)


def is_network_error(error_text: str | None) -> bool:
    """True if ``error_text`` looks like a transient network failure.

    Used by the auto-resume path to decide which failed episodes to
    re-queue when connectivity is restored.
    """
    return any(h in (error_text or "") for h in _NET_HINTS)


class ConnectivityMonitor(QObject):
    """Background thread that probes connectivity periodically.

    Emits ``online_changed(bool)`` ONLY when the state flips, never on
    steady state — UI consumers can wire it directly without
    debouncing. Probes every 30 s when online, every 5 s when offline
    so reconnect is detected quickly.

    A plain ``threading.Thread`` is used (not QThread) to avoid Qt
    re-entrancy headaches inside short-lived test fixtures; PyQt
    ``pyqtSignal`` emit is thread-safe and marshals to the receiver's
    event loop automatically.
    """

    online_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._stop = False
        self._last_state: bool | None = None
        self._worker: threading.Thread | None = None

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return  # idempotent — second call is a no-op

        def loop() -> None:
            while not self._stop:
                online = is_online()
                if online != self._last_state:
                    self._last_state = online
                    self.online_changed.emit(online)
                # Recover faster than we detect drops — once offline,
                # poll every 5 s so the user sees "back online" quickly.
                time.sleep(30 if online else 5)

        self._worker = threading.Thread(target=loop, name="connectivity", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop = True
