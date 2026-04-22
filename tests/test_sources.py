import pytest

from core.models import Settings
from core.sources import (
    SourcesError,
    podcasts_enabled,
    validate_sources,
    youtube_enabled,
)


def test_defaults_both_on():
    s = Settings()
    assert podcasts_enabled(s)
    assert youtube_enabled(s)


def test_youtube_off_when_unchecked():
    s = Settings(sources_youtube=False)
    assert not youtube_enabled(s)


def test_at_least_one_required():
    s = Settings(sources_podcasts=False, sources_youtube=False)
    with pytest.raises(SourcesError):
        validate_sources(s)


def test_validate_passes_when_one_checked():
    validate_sources(Settings(sources_podcasts=False, sources_youtube=True))
    validate_sources(Settings(sources_podcasts=True, sources_youtube=False))
