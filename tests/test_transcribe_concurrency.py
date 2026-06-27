"""Parallel-transcription worker resolution (2.2)."""

from __future__ import annotations

from core.load import resolve_transcribe_workers


def test_default_keeps_profile_choice():
    # transcribe_concurrency == 1 (default) must not reduce a "full" profile's 2.
    assert resolve_transcribe_workers(2, 1) == 2
    assert resolve_transcribe_workers(1, 1) == 1


def test_override_raises_cap():
    assert resolve_transcribe_workers(1, 4) == 4
    assert resolve_transcribe_workers(2, 3) == 3


def test_floors_at_one():
    assert resolve_transcribe_workers(0, 0) == 1
    assert resolve_transcribe_workers(0, 1) == 1
