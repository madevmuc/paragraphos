"""Flag-gated diarization skeleton (1.5)."""

from __future__ import annotations

import pytest

from core.diarize import DiarizationUnavailable, diarize_segments


def test_disabled_is_noop():
    assert diarize_segments("/tmp/whatever.wav", enabled=False) == []


def test_enabled_raises_until_backend_lands():
    with pytest.raises(DiarizationUnavailable):
        diarize_segments("/tmp/whatever.wav", enabled=True)
