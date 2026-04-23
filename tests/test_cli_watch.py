"""CLI smoke for `paragraphos watch …`."""

from pathlib import Path


def test_watch_add_enables_and_sets_root(tmp_path: Path, monkeypatch):
    support = tmp_path / "support"
    support.mkdir()
    # match the pattern from test_cli_ingest.py
    import cli

    monkeypatch.setattr(cli, "DATA", support)

    root = tmp_path / "z"
    root.mkdir()

    from core.models import Settings

    Settings().save(support / "settings.yaml")

    import argparse

    rc = cli.cmd_watch_add(argparse.Namespace(path=str(root)))
    assert rc == 0
    s = Settings.load(support / "settings.yaml")
    assert s.watch_folder_enabled is True
    assert Path(s.watch_folder_root).expanduser() == root


def test_watch_remove_disables(tmp_path: Path, monkeypatch):
    support = tmp_path / "support"
    support.mkdir()
    import cli

    monkeypatch.setattr(cli, "DATA", support)

    from core.models import Settings

    s = Settings(watch_folder_enabled=True, watch_folder_root=str(tmp_path / "z"))
    s.save(support / "settings.yaml")

    import argparse

    rc = cli.cmd_watch_remove(argparse.Namespace())
    assert rc == 0
    assert Settings.load(support / "settings.yaml").watch_folder_enabled is False
