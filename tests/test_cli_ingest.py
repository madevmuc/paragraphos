"""CLI smoke for `paragraphos ingest …` subcommands.

Validates that `cmd_ingest_file` (and by extension the sibling url/folder
cmds) return rc=0 on a happy path, without reaching for real ffprobe or
mutating the user's Application Support directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from core.models import Watchlist
from core.state import StateStore


def test_ingest_file_cli_returns_guid(tmp_path: Path, monkeypatch):
    # Point the CLI at a disposable data dir so state.sqlite /
    # watchlist.yaml land in tmp_path, not ~/Library.
    support = tmp_path / "support"
    support.mkdir()

    import cli

    monkeypatch.setattr(cli, "DATA", support)

    state = StateStore(support / "state.sqlite")
    state.init_schema()
    Watchlist().save(support / "watchlist.yaml")

    (tmp_path / "a.wav").write_bytes(b"x")
    src = tmp_path / "a.wav"

    monkeypatch.setattr("core.local_source.has_audio_stream", lambda p: True)
    monkeypatch.setattr("core.local_source.duration_seconds", lambda p: 10)

    args = argparse.Namespace(path=str(src), show=None)
    rc = cli.cmd_ingest_file(args)
    assert rc == 0
