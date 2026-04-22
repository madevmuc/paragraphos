"""Dependency check: Homebrew / whisper-cpp / ffmpeg / whisper model."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

_WHISPER_CANDIDATES = (
    "/opt/homebrew/bin/whisper-cli",  # Apple Silicon
    "/usr/local/bin/whisper-cli",  # Intel Mac
    "/opt/local/bin/whisper-cli",  # MacPorts
)
WHISPER_BIN = _WHISPER_CANDIDATES[0]
MODEL_DIR = Path.home() / ".config" / "open-wispr" / "models"
DEFAULT_MODEL = "ggml-large-v3-turbo.bin"


@dataclass
class DepStatus:
    brew: bool = False
    whisper_cli: bool = False
    ffmpeg: bool = False
    model: bool = False

    @property
    def all_ok(self) -> bool:
        return self.brew and self.whisper_cli and self.ffmpeg and self.model

    def missing(self) -> list[str]:
        out = []
        if not self.brew:
            out.append("Homebrew")
        if not self.whisper_cli:
            out.append("whisper-cpp")
        if not self.ffmpeg:
            out.append("ffmpeg")
        if not self.model:
            out.append(f"{DEFAULT_MODEL}")
        return out


_BREW_CANDIDATES = (
    "/opt/homebrew/bin/brew",  # Apple Silicon
    "/usr/local/bin/brew",  # Intel Mac
    "/opt/local/bin/brew",  # uncommon legacy
)
_FFMPEG_CANDIDATES = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/opt/local/bin/ffmpeg",
)

# Homebrew bin dirs that may not be on PATH when the .app is launched
# from Finder/launchd — `shutil.which` by default only looks in the
# inherited PATH which on macOS GUI apps is typically `/usr/bin:/bin:
# /usr/sbin:/sbin`. Merge our own Homebrew-aware path list so a fresh
# brew install is detected on Recheck even before the user restarts.
_EXTRA_PATH = ":".join(["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"])


def _has_any(paths: tuple[str, ...], name: str) -> bool:
    import os as _os

    search_path = _EXTRA_PATH
    env_path = _os.environ.get("PATH", "")
    if env_path:
        search_path = env_path + ":" + search_path
    if shutil.which(name, path=search_path):
        return True
    return any(Path(p).exists() for p in paths)


def _brew_env() -> dict[str, str]:
    """Env for subprocess.run([brew,...]) that prepends the common Homebrew
    bin dirs so a Finder-launched .app can find `brew` right after a fresh
    install without relaunching."""
    import os as _os

    env = _os.environ.copy()
    path = env.get("PATH", "")
    env["PATH"] = _EXTRA_PATH + (":" + path if path else "")
    return env


def check() -> DepStatus:
    s = DepStatus()
    s.brew = _has_any(_BREW_CANDIDATES, "brew")
    s.whisper_cli = _has_any(_WHISPER_CANDIDATES, "whisper-cli")
    s.ffmpeg = _has_any(_FFMPEG_CANDIDATES, "ffmpeg")
    s.model = (MODEL_DIR / DEFAULT_MODEL).exists()
    return s


def install_brew_command() -> str:
    """The one-liner from brew.sh — user runs in Terminal, must sudo once."""
    return (
        '/bin/bash -c "$(curl -fsSL '
        'https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    )


def install_whisper_cpp() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["brew", "install", "whisper-cpp"], capture_output=True, text=True, env=_brew_env()
    )


def install_ffmpeg() -> subprocess.CompletedProcess:
    return subprocess.run(
        ["brew", "install", "ffmpeg"], capture_output=True, text=True, env=_brew_env()
    )
