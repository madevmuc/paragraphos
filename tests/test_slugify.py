import pytest

from core.sanitize import slugify


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Tech! Podcast — Show", "tech-podcast-show"),
        ("  Multiple   Spaces ", "multiple-spaces"),
        ("Die Drei ???", "die-drei"),
        ("C'est la vie", "c-est-la-vie"),
        ("Emojis 🎙 dropped", "emojis-dropped"),
        ("", "show"),
        ("---", "show"),
        ("Über Café", "uber-cafe"),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected
