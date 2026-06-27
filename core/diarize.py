"""Speaker diarization — flag-gated skeleton (roadmap 1.5).

Full local diarization (sherpa-onnx, Apache-2.0, + a one-time model download) is
**not** built in this run — see ``docs/plans/diarization-design.md`` for the
integration plan. This module provides the seam the rest of the app calls:
``diarize_segments`` is a no-op when ``diarization_enabled`` is off (the default)
and raises a clear "not yet available" error when explicitly enabled, so nothing
silently mis-behaves.
"""

from __future__ import annotations

from dataclasses import dataclass


class DiarizationUnavailable(RuntimeError):
    """Diarization was requested but the backend isn't installed/built yet."""


@dataclass
class SpeakerSegment:
    start: float
    end: float
    speaker: str  # "A", "B", … assigned in order of first appearance


def diarize_segments(audio_path, *, enabled: bool):
    """Return speaker segments for ``audio_path``.

    Skeleton contract (1.5): when ``enabled`` is False this is a no-op and
    returns ``[]`` (callers leave the transcript unchanged). When True it raises
    :class:`DiarizationUnavailable` until the sherpa-onnx backend lands — better
    a clear error than a silent no-op when the user opted in."""
    if not enabled:
        return []
    raise DiarizationUnavailable(
        "speaker diarization isn't available yet — see "
        "docs/plans/diarization-design.md. Disable diarization_enabled to proceed."
    )
