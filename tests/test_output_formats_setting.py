from core.models import Settings


def test_save_srt_default_on():
    assert Settings().save_srt is True


def test_save_srt_can_be_disabled():
    s = Settings()
    s.save_srt = False
    assert s.save_srt is False
