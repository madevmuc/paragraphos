"""Non-blocking GitHub-release version check.

Runs once at startup in a daemon thread. Compares the installed bundle
version (CFBundleShortVersionString) against the latest GitHub release
tag and surfaces a tray notification if newer.

The app itself is not modified — the user downloads manually. Keeps
things simple and avoids the code-signing chain Sparkle-style auto-
upgrade would need.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from core.http import get_client

logger = logging.getLogger(__name__)

# Override in tests or when someone forks the repo.
DEFAULT_GITHUB_REPO = "m4ma/paragraphos"


def _parse_semver(tag: str) -> tuple[int, int, int]:
    """Return `(major, minor, patch)` from `v0.5.0` / `0.5.0` / `0.5.0-beta`."""
    s = tag.strip().lstrip("vV")
    if "-" in s:
        s = s.split("-", 1)[0]
    parts = s.split(".")
    def _num(p: str) -> int:
        n = ""
        for ch in p:
            if ch.isdigit():
                n += ch
            else:
                break
        return int(n) if n else 0
    while len(parts) < 3:
        parts.append("0")
    return _num(parts[0]), _num(parts[1]), _num(parts[2])


def is_newer(remote: str, local: str) -> bool:
    return _parse_semver(remote) > _parse_semver(local)


def check_for_update(local_version: str,
                     on_update_available: Callable[[str, str], None],
                     *, repo: Optional[str] = None,
                     timeout: float = 8.0) -> None:
    """Fire-and-forget: starts a daemon thread, calls
    on_update_available(remote_tag, url) if a newer version is out.
    Silent on network errors."""
    repo_slug = repo or DEFAULT_GITHUB_REPO
    releases_api = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    def run() -> None:
        try:
            r = get_client().get(releases_api, timeout=timeout,
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "paragraphos/updater"})
            if r.status_code != 200:
                return
            data = r.json()
            tag = data.get("tag_name", "")
            url = data.get("html_url", "")
            if tag and is_newer(tag, local_version):
                on_update_available(tag, url)
        except Exception as e:
            logger.debug("update check failed: %s", e)
    threading.Thread(target=run, daemon=True).start()
