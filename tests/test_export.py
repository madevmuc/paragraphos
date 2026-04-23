"""Tests for core.export markdown renderer."""

from __future__ import annotations


def test_youtube_frontmatter_fields():
    from core.export import render_episode_markdown

    md = render_episode_markdown(
        show_slug="myshow",
        title="Episode 1",
        srt_text="1\n00:00:00,000 --> 00:00:01,000\nHi\n",
        source="youtube",
        youtube_id="dQw4w9WgXcQ",
        channel_id="UCabc",
        transcript_source="captions",
    )
    assert "source: youtube" in md
    assert "youtube_id: dQw4w9WgXcQ" in md
    assert "youtube_url: https://youtu.be/dQw4w9WgXcQ" in md
    assert "channel_id: UCabc" in md
    assert "transcript_source: captions" in md
    assert "[Watch on YouTube](https://youtu.be/dQw4w9WgXcQ)" in md


def test_podcast_default_omits_youtube_fields():
    from core.export import render_episode_markdown

    md = render_episode_markdown(
        show_slug="myshow",
        title="Episode 1",
        srt_text="1\n00:00:00,000 --> 00:00:01,000\nHi\n",
    )
    # Default source must remain podcast-flavoured and free of YouTube noise.
    assert "youtube_id" not in md
    assert "youtube_url" not in md
    assert "channel_id" not in md
    assert "Watch on YouTube" not in md
    assert "source: youtube" not in md
