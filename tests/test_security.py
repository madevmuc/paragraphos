from pathlib import Path

import pytest

from core.security import (PathEscapeError, UnsafeURLError,
                            is_allowed_audio_content_type, safe_path_within,
                            safe_url, sha256_of, verify_model)


# ── URL safety ───────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "file:///etc/passwd",
    "file:///Users/me/.ssh/id_rsa",
    "data:text/html,<script>alert(1)</script>",
    "javascript:alert(1)",
    "",
    "   ",
])
def test_safe_url_refuses_non_http(bad):
    with pytest.raises(UnsafeURLError):
        safe_url(bad)


@pytest.mark.parametrize("url", [
    "http://localhost/rss",
    "http://127.0.0.1/feed",
    "http://10.0.0.1/x",
    "http://192.168.1.1/x",
    "http://[::1]/x",
])
def test_safe_url_refuses_private_ips(url):
    with pytest.raises(UnsafeURLError):
        safe_url(url)


def test_safe_url_accepts_public():
    assert safe_url("https://example.com/rss") == "https://example.com/rss"
    assert safe_url("http://example.com/feed") == "http://example.com/feed"


def test_safe_url_private_override_allowed():
    # For future test harnesses / debugging
    assert safe_url("http://127.0.0.1/rss", allow_private=True) \
        == "http://127.0.0.1/rss"


def test_allowed_audio_content_types():
    assert is_allowed_audio_content_type("audio/mpeg")
    assert is_allowed_audio_content_type("audio/mp4;codecs=mp4a.40.2")
    assert is_allowed_audio_content_type("application/ogg")
    assert not is_allowed_audio_content_type("text/html")
    assert not is_allowed_audio_content_type("application/json")
    assert not is_allowed_audio_content_type("")


# ── Path traversal ───────────────────────────────────────────

def test_safe_path_within_accepts_child(tmp_path: Path):
    out = tmp_path / "out"; out.mkdir()
    target = out / "show" / "file.md"
    assert safe_path_within(out, target) == target.resolve()


def test_safe_path_within_rejects_parent(tmp_path: Path):
    out = tmp_path / "out"; out.mkdir()
    bad = out / ".." / "escaped.md"
    with pytest.raises(PathEscapeError):
        safe_path_within(out, bad)


def test_safe_path_within_rejects_absolute_elsewhere(tmp_path: Path):
    out = tmp_path / "out"; out.mkdir()
    with pytest.raises(PathEscapeError):
        safe_path_within(out, Path("/etc/passwd"))


# ── Model integrity ──────────────────────────────────────────

def test_sha256_of(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world")
    # known sha256 of "hello world"
    assert sha256_of(p) == \
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_verify_model_first_use_pins_hash(tmp_path: Path, monkeypatch):
    from core import security
    pin_file = tmp_path / "pins.yaml"
    monkeypatch.setattr(security, "_model_hashes_path", lambda: pin_file)
    p = tmp_path / "x.bin"; p.write_bytes(b"foo")
    verify_model(p, "new-model")  # first time — pins the sha
    assert pin_file.exists()
    assert "new-model" in security._load_pinned_hashes()


def test_verify_model_second_use_matches(tmp_path: Path, monkeypatch):
    from core import security
    pin_file = tmp_path / "pins.yaml"
    monkeypatch.setattr(security, "_model_hashes_path", lambda: pin_file)
    p = tmp_path / "x.bin"; p.write_bytes(b"foo")
    verify_model(p, "m")  # pins
    verify_model(p, "m")  # matches — no error


def test_verify_model_mismatch_raises(tmp_path: Path, monkeypatch):
    from core import security
    pin_file = tmp_path / "pins.yaml"
    monkeypatch.setattr(security, "_model_hashes_path", lambda: pin_file)
    p = tmp_path / "x.bin"; p.write_bytes(b"foo")
    verify_model(p, "m")  # pins sha256(b"foo")
    p.write_bytes(b"bar")  # file swapped on disk
    with pytest.raises(ValueError, match="SHA256 changed"):
        verify_model(p, "m")
