"""Hardware / OS compatibility check for first-run wizard.

Blocking vs advisory:
    Blocking — wizard refuses to continue (arch, macOS version).
    Advisory — wizard warns but lets the user continue (RAM, free disk).
"""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path

MIN_MACOS = (13, 0)
ADVISORY_MIN_RAM_GB = 8
ADVISORY_MIN_FREE_DISK_GB = 3


def _machine() -> str:
    return platform.machine()


def _mac_ver() -> tuple[str, tuple[str, str, str], str]:
    return platform.mac_ver()


def _total_memory_gb() -> float:
    # psutil is optional; fall back to sysctl if missing.
    try:
        import psutil

        return psutil.virtual_memory().total / (1024**3)
    except Exception:
        import subprocess

        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
        try:
            return int(out.stdout.strip()) / (1024**3)
        except ValueError:
            return 0.0


def _free_disk_gb() -> float:
    try:
        return shutil.disk_usage(str(Path.home())).free / (1024**3)
    except OSError:
        return 0.0


@dataclass
class CompatStatus:
    blocking_reasons: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)

    @property
    def all_blocking_ok(self) -> bool:
        return not self.blocking_reasons


def _parse_macos_major_minor(ver_str: str) -> tuple[int, int]:
    parts = ver_str.split(".")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return (0, 0)


def check_compat() -> CompatStatus:
    s = CompatStatus()

    arch = _machine()
    if arch != "arm64":
        s.blocking_reasons.append(f"Apple Silicon required — this Mac reports arch '{arch}'.")

    mac = _mac_ver()[0]
    major, minor = _parse_macos_major_minor(mac)
    if (major, minor) < MIN_MACOS:
        s.blocking_reasons.append(
            f"macOS {MIN_MACOS[0]}.{MIN_MACOS[1]}+ required — this Mac reports {mac}."
        )

    ram = _total_memory_gb()
    if 0 < ram < ADVISORY_MIN_RAM_GB:
        s.advisories.append(
            f"Only {ram:.0f} GB RAM detected — transcription will be slow (≥ 8 GB recommended)."
        )

    free = _free_disk_gb()
    if 0 < free < ADVISORY_MIN_FREE_DISK_GB:
        s.advisories.append(f"Only {free:.0f} GB free disk — installation needs ~3 GB.")

    return s
