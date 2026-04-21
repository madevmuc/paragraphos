from core.sanitize import sanitize_filename


def test_preserves_umlauts():
    assert sanitize_filename("Wohnräume für Anfänger") == "Wohnräume für Anfänger"


def test_preserves_eszett():
    assert sanitize_filename("Straße & Größe") == "Straße & Größe"


def test_strips_forbidden_fs_chars():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"


def test_strips_control_chars():
    assert sanitize_filename("hello\x00\x01\x1fworld") == "helloworld"


def test_collapses_whitespace():
    assert sanitize_filename("foo   bar") == "foo bar"


def test_trims_leading_trailing_dots_and_spaces():
    assert sanitize_filename("  .foo.  ") == "foo"


def test_truncates_very_long_name():
    long = "ä" * 300
    out = sanitize_filename(long)
    assert len(out.encode("utf-8")) <= 200
    assert out.startswith("ä")


def test_empty_becomes_placeholder():
    assert sanitize_filename("///") == "_"
    assert sanitize_filename("") == "_"
