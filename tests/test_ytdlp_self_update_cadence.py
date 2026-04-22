from datetime import datetime, timedelta, timezone

import pytest  # noqa: F401

from core.models import Settings


def test_self_update_runs_when_never_run(monkeypatch):
    from ui.main_window import maybe_self_update_ytdlp

    s = Settings(sources_youtube=True, ytdlp_last_self_update_at="")
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr(
        "core.ytdlp.self_update",
        lambda: called.__setitem__("ran", True),
    )
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert called["ran"] is True


def test_self_update_skipped_within_7_days(monkeypatch):
    from ui.main_window import maybe_self_update_ytdlp

    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    s = Settings(sources_youtube=True, ytdlp_last_self_update_at=recent)
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr(
        "core.ytdlp.self_update",
        lambda: called.__setitem__("ran", True),
    )
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert called["ran"] is False


def test_self_update_skipped_when_youtube_disabled(monkeypatch):
    from ui.main_window import maybe_self_update_ytdlp

    s = Settings(sources_youtube=False)
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr(
        "core.ytdlp.self_update",
        lambda: called.__setitem__("ran", True),
    )
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert called["ran"] is False


def test_self_update_skipped_when_not_installed(monkeypatch):
    from ui.main_window import maybe_self_update_ytdlp

    s = Settings(sources_youtube=True, ytdlp_last_self_update_at="")
    called = {"ran": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: False)
    monkeypatch.setattr(
        "core.ytdlp.self_update",
        lambda: called.__setitem__("ran", True),
    )
    maybe_self_update_ytdlp(s, save=lambda: None)
    assert called["ran"] is False


def test_self_update_persists_timestamp_on_success(monkeypatch):
    from ui.main_window import maybe_self_update_ytdlp

    s = Settings(sources_youtube=True, ytdlp_last_self_update_at="")
    saved = {"called": False}
    monkeypatch.setattr("core.ytdlp.is_installed", lambda: True)
    monkeypatch.setattr("core.ytdlp.self_update", lambda: None)
    maybe_self_update_ytdlp(s, save=lambda: saved.__setitem__("called", True))
    assert s.ytdlp_last_self_update_at != ""
    assert saved["called"] is True
