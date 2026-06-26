"""App-wide activity log.

A single place for user-facing actions — adding/removing a show, starting,
pausing or stopping the queue, deleting transcripts, queue edits, … — to
surface in the GUI Log dock + Logs pane AND the on-disk log file.

The GUI sink is installed once by ``MainWindow`` (it fans into the dock and the
sidebar pane). Every message is also written to the ``paragraphos.activity``
logger so it lands in the rotating log file even when no window is attached
(headless / tests). Call :func:`log` from any GUI-thread handler.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

_logger = logging.getLogger("paragraphos.activity")
_sink: Optional[Callable[[str], None]] = None


def set_sink(fn: Optional[Callable[[str], None]]) -> None:
    """Install (or clear) the GUI sink. Called once by ``MainWindow``."""
    global _sink
    _sink = fn


def log(msg: str) -> None:
    """Record a user-facing action — to the log file and (if attached) the dock."""
    _logger.info(msg)
    if _sink is not None:
        try:
            _sink(msg)
        except Exception:  # noqa: BLE001 — the log must never break an action
            pass
