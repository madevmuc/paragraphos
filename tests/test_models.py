from pathlib import Path

import pytest

from core.models import Settings, Show, Watchlist


def test_show_defaults():
    s = Show(slug="test", title="Test", rss="https://example.com/feed.xml")
    assert s.enabled is True
    assert s.whisper_prompt == ""
    assert s.output_override is None


def test_watchlist_roundtrip(tmp_path: Path):
    wl = Watchlist(
        shows=[
            Show(slug="foo", title="Foo", rss="https://foo.test/rss", whisper_prompt="Host Alice"),
        ]
    )
    p = tmp_path / "wl.yaml"
    wl.save(p)
    loaded = Watchlist.load(p)
    assert loaded == wl


def test_settings_defaults_match_design(tmp_path: Path):
    # Settings() gives the generic defaults; Settings.load() on a fresh
    # install now overlays HW-aware tuning recommendations for
    # parallel_transcribe + whisper_multiproc (see T15), so assert the
    # generic defaults against the constructor instead.
    s = Settings()
    assert s.daily_check_time == "09:00"
    assert s.catch_up_missed is True
    assert s.notify_on_success is True
    assert s.mp3_retention_days == 7
    assert s.delete_mp3_after_transcribe is True
    assert s.bandwidth_limit_mbps == 0
    assert s.parallel_transcribe == 1


def test_settings_time_validation():
    with pytest.raises(ValueError):
        Settings(daily_check_time="25:99")
    with pytest.raises(ValueError):
        Settings(daily_check_time="9am")


def test_show_source_defaults_to_podcast():
    from core.models import Show

    s = Show(slug="x", title="X", rss="https://x/feed.xml")
    assert s.source == "podcast"


def test_show_source_accepts_youtube():
    from core.models import Show

    s = Show(
        slug="x",
        title="X",
        rss="https://youtube.com/feeds/videos.xml?channel_id=UC...",
        source="youtube",
    )
    assert s.source == "youtube"
