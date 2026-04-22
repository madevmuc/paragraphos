import pytest

from core.youtube import (
    YoutubeUrl,
    YoutubeUrlError,
    parse_youtube_url,
    rss_url_for_channel_id,
)


@pytest.mark.parametrize(
    "url,expected_kind,expected_value",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "video", "dQw4w9WgXcQ"),
        (
            "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw",
            "channel_id",
            "UCuAXFkgsw1L7xaCfnd5JJOw",
        ),
        ("https://www.youtube.com/@MrBeast", "handle", "MrBeast"),
        ("https://youtube.com/@MrBeast/videos", "handle", "MrBeast"),
    ],
)
def test_parse_known_forms(url, expected_kind, expected_value):
    p = parse_youtube_url(url)
    assert p.kind == expected_kind
    assert p.value == expected_value


def test_parse_rejects_unknown():
    with pytest.raises(YoutubeUrlError):
        parse_youtube_url("https://example.com/x")


def test_rss_url_for_channel_id():
    assert (
        rss_url_for_channel_id("UC123")
        == "https://www.youtube.com/feeds/videos.xml?channel_id=UC123"
    )
