"""Central logging — rotating file under data/logs/paragraphos-YYYY-MM-DD.log."""

from __future__ import annotations

import logging
import logging.handlers
from datetime import datetime, timedelta
from pathlib import Path


def setup_logging(data_dir: Path, retention_days: int = 90) -> Path:
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "paragraphos.log"

    handler = logging.handlers.TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=retention_days,
        encoding="utf-8",
        delay=True,
    )
    handler.suffix = "%Y-%m-%d"
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Avoid duplicating if setup_logging is called twice.
    if not any(isinstance(h, logging.handlers.TimedRotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)

    # Prune anything older than retention_days even if backupCount drifted.
    _cutoff = datetime.now() - timedelta(days=retention_days)
    for f in logs_dir.glob("paragraphos.log.*"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime) < _cutoff:
                f.unlink()
        except OSError:
            pass
    return log_file
