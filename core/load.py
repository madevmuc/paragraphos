"""Load-management profiles — map a user-facing background-load level to
concrete whisper-cli launch parameters (parallelism, threads, macOS
scheduling tier).

Pure + dependency-free so it unit-tests without touching hardware. The
caller (ui/worker_thread.py) supplies the detected performance-core count;
core/hw.py does the detection. macOS scheduling tiers are applied as an
argv prefix on the whisper-cli command (thread-safe — no preexec_fn).

Design: docs/plans/2026-06-25-load-management-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LoadLevel = Literal["quiet", "balanced", "full"]
Qos = Literal["background", "nice", "normal"]


@dataclass(frozen=True)
class LoadProfile:
    parallel: int  # concurrent transcribe workers (whisper-cli processes)
    threads: int  # whisper-cli -t
    qos: Qos  # macOS scheduling tier
    nice_level: int  # niceness when qos == "nice" (ignored otherwise)

    def command_prefix(self) -> list[str]:
        """argv prefix that applies the scheduling tier to a launched
        subprocess. Empty list for the normal tier."""
        if self.qos == "background":
            return ["taskpolicy", "-b"]
        if self.qos == "nice":
            return ["nice", "-n", str(self.nice_level)]
        return []


def resolve_load_profile(
    level: LoadLevel,
    *,
    perf_cores: int,
    background_priority: bool,
) -> LoadProfile:
    """Map (level, hardware, polite-flag) → concrete launch parameters.

    ``perf_cores`` is the machine's performance-core count; the caller falls
    back to logical CPUs / a small constant when detection fails. Higher
    levels spend more cores and a less-deferential scheduling tier.
    """
    p = max(1, perf_cores)
    if level == "quiet":
        return LoadProfile(parallel=1, threads=min(2, p), qos="background", nice_level=0)
    if level == "balanced":
        return LoadProfile(parallel=1, threads=max(2, p // 2), qos="nice", nice_level=10)
    if level == "full":
        parallel = 2 if p >= 8 else 1
        threads = max(2, p // parallel)
        if background_priority:
            return LoadProfile(parallel=parallel, threads=threads, qos="nice", nice_level=5)
        return LoadProfile(parallel=parallel, threads=threads, qos="normal", nice_level=0)
    raise ValueError(f"unknown load level: {level!r}")


_TIER_DE = {
    "background": "läuft im Hintergrund (E-Kerne)",
    "nice": "weicht aktiver Nutzung aus",
    "normal": "volle Priorität",
}


def describe_profile(profile: LoadProfile) -> str:
    """Human-readable one-liner for the settings read-out label."""
    episodes = "1 Episode" if profile.parallel == 1 else f"{profile.parallel} Episoden"
    return f"{episodes} × {profile.threads} Threads · {_TIER_DE[profile.qos]}"
