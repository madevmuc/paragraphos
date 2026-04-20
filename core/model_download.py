"""Download whisper.cpp GGML models from Hugging Face."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from core.http import get_client

MODEL_DIR = Path.home() / ".config" / "open-wispr" / "models"
BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
AVAILABLE = {
    "base": "ggml-base.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
    "large-v3": "ggml-large-v3.bin",
    "large-v3-turbo": "ggml-large-v3-turbo.bin",
}


def _target_path(name: str) -> Path:
    return MODEL_DIR / f"ggml-{name}.bin"


def is_installed(name: str) -> bool:
    return _target_path(name).exists()


def download_model(name: str, on_progress: Callable[[int, int], None] | None = None) -> Path:
    from core.security import safe_url, verify_model

    if name not in AVAILABLE:
        raise ValueError(f"unknown model {name!r}")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    url = BASE_URL + AVAILABLE[name]
    safe_url(url)  # HTTPS, non-private host
    dst = _target_path(name)
    tmp = dst.with_suffix(".bin.part")
    written = 0
    with get_client().stream("GET", url, follow_redirects=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", "0") or 0)
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
                written += len(chunk)
                if on_progress:
                    on_progress(written, total)
    # Verify before moving into place — bad download stays in .part and gets
    # retried next time.
    try:
        verify_model(tmp, name)
    except ValueError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    tmp.replace(dst)
    return dst


def download_model_async(name: str, on_done: Callable[[bool, str], None]) -> None:
    """Fire-and-forget — calls on_done(ok, error_message) from a background thread.

    UI code should marshal on_done back to the GUI thread via QTimer.singleShot
    or a Qt signal if it touches widgets.
    """

    def run():
        try:
            download_model(name)
            on_done(True, "")
        except Exception as e:
            on_done(False, str(e))

    threading.Thread(target=run, daemon=True).start()
