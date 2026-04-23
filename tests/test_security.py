from pathlib import Path

import pytest

from core.security import (
    PathEscapeError,
    UnsafeURLError,
    is_allowed_audio_content_type,
    safe_path_within,
    safe_url,
    sha256_of,
    verify_model,
)

# ── URL safety ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        "file:///etc/passwd",
        "file:///Users/me/.ssh/id_rsa",
        "data:text/html,<script>alert(1)</script>",
        "javascript:alert(1)",
        "",
        "   ",
    ],
)
def test_safe_url_refuses_non_http(bad):
    with pytest.raises(UnsafeURLError):
        safe_url(bad)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/rss",
        "http://127.0.0.1/feed",
        "http://10.0.0.1/x",
        "http://192.168.1.1/x",
        "http://[::1]/x",
    ],
)
def test_safe_url_refuses_private_ips(url):
    with pytest.raises(UnsafeURLError):
        safe_url(url)


def test_safe_url_accepts_public():
    assert safe_url("https://example.com/rss") == "https://example.com/rss"
    assert safe_url("http://example.com/feed") == "http://example.com/feed"


def test_safe_url_private_override_allowed():
    # For future test harnesses / debugging
    assert safe_url("http://127.0.0.1/rss", allow_private=True) == "http://127.0.0.1/rss"


def test_safe_url_accepts_ipv4_mapped_ipv6_for_public_host(monkeypatch):
    """Regression: macOS DNS64/NAT64 / Happy Eyeballs sometimes returns
    IPv4-mapped IPv6 addresses (``::ffff:x.x.x.x``) from getaddrinfo for
    plain IPv4 hosts. Python's ``ipaddress`` module marks those as
    ``is_reserved=True`` (the ``::ffff:0:0/96`` block per RFC 4291), so
    without the unwrap in ``_is_private_ip`` the SSRF guard rejects
    every public podcast host with a misleading "private-network host"
    error. This actually shipped to a user as a wave of feed failures.
    """
    import socket

    def fake_getaddrinfo(host, _port, *_a, **_kw):
        # Mimic the macOS behaviour: a single IPv4-mapped IPv6 result for
        # a plain public IPv4 host (here, an actual podigee.io address).
        return [(socket.AF_INET6, 0, 0, "", ("::ffff:162.55.189.14", 0, 0, 0))]

    monkeypatch.setattr("core.security.socket.getaddrinfo", fake_getaddrinfo)
    # Should NOT raise.
    assert safe_url("https://immocation.podigee.io/feed/mp3") == (
        "https://immocation.podigee.io/feed/mp3"
    )


def test_safe_url_still_blocks_real_private_ipv6(monkeypatch):
    """The IPv4-mapped unwrap must not weaken the IPv6 path. Real
    private IPv6 (``fc00::/7``, link-local ``fe80::/10``, loopback
    ``::1``) must still trip the guard."""
    import socket

    def fake_getaddrinfo(host, _port, *_a, **_kw):
        return [(socket.AF_INET6, 0, 0, "", ("fe80::1", 0, 0, 0))]

    monkeypatch.setattr("core.security.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError):
        safe_url("https://example.com/feed")


def test_safe_url_accepts_nat64_synthesised_public_ipv4(monkeypatch):
    """Regression: macOS resolvers on NAT64 / IPv6-only LANs synthesise
    addresses in the well-known prefix ``64:ff9b::/96`` (RFC 6052).
    Python's ``ipaddress`` marks the whole prefix as reserved (it's the
    IANA "IPv4/IPv6 Translators" registration), so without the NAT64
    unwrap, every IPv4-only public feed host fails SSRF screening on
    those networks. This shipped to a user — `gvh.podcaster.de` →
    `64:ff9b::5e82:dfe4` (== 94.130.223.228, public)."""
    import socket

    # 94.130.223.228 in NAT64 form — gvh.podcaster.de's actual public IP.
    def fake_getaddrinfo(host, _port, *_a, **_kw):
        return [(socket.AF_INET6, 0, 0, "", ("64:ff9b::5e82:dfe4", 0, 0, 0))]

    monkeypatch.setattr("core.security.socket.getaddrinfo", fake_getaddrinfo)
    assert safe_url("https://gvh.podcaster.de/grundeigentuemerverband.rss") == (
        "https://gvh.podcaster.de/grundeigentuemerverband.rss"
    )


def test_safe_url_blocks_nat64_wrapping_a_private_ipv4(monkeypatch):
    """The NAT64 unwrap must not become an SSRF bypass: if a NAT64
    synthesised address embeds a private IPv4 (e.g. someone tricks the
    resolver into ``64:ff9b::a00:1`` == 10.0.0.1), the guard must still
    block."""
    import socket

    # 10.0.0.1 in NAT64 form.
    def fake_getaddrinfo(host, _port, *_a, **_kw):
        return [(socket.AF_INET6, 0, 0, "", ("64:ff9b::a00:1", 0, 0, 0))]

    monkeypatch.setattr("core.security.socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeURLError):
        safe_url("https://example.com/feed")


@pytest.mark.parametrize(
    "ct",
    [
        "audio/mpeg",
        "audio/mp4",
        "audio/mp4;codecs=mp4a.40.2",
        "application/ogg",
        "application/octet-stream",
        "binary/octet-stream",
        "audio/mpeg; charset=binary",
    ],
)
def test_allowed_audio_content_types(ct):
    assert is_allowed_audio_content_type(ct)


@pytest.mark.parametrize(
    "ct",
    [
        "text/html",
        "application/json",
        "image/png",
        "video/mp4",
        "",
    ],
)
def test_rejected_content_types(ct):
    assert not is_allowed_audio_content_type(ct)


# ── Path traversal ───────────────────────────────────────────


def test_safe_path_within_accepts_child(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    target = out / "show" / "file.md"
    assert safe_path_within(out, target) == target.resolve()


def test_safe_path_within_rejects_parent(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    bad = out / ".." / "escaped.md"
    with pytest.raises(PathEscapeError):
        safe_path_within(out, bad)


def test_safe_path_within_rejects_absolute_elsewhere(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(PathEscapeError):
        safe_path_within(out, Path("/etc/passwd"))


# ── Model integrity ──────────────────────────────────────────


def test_sha256_of(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"hello world")
    # known sha256 of "hello world"
    assert sha256_of(p) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_verify_model_first_use_pins_hash(tmp_path: Path, monkeypatch):
    from core import security

    pin_file = tmp_path / "pins.yaml"
    monkeypatch.setattr(security, "_model_hashes_path", lambda: pin_file)
    p = tmp_path / "x.bin"
    p.write_bytes(b"foo")
    verify_model(p, "new-model")  # first time — pins the sha
    assert pin_file.exists()
    assert "new-model" in security._load_pinned_hashes()


def test_verify_model_second_use_matches(tmp_path: Path, monkeypatch):
    from core import security

    pin_file = tmp_path / "pins.yaml"
    monkeypatch.setattr(security, "_model_hashes_path", lambda: pin_file)
    p = tmp_path / "x.bin"
    p.write_bytes(b"foo")
    verify_model(p, "m")  # pins
    verify_model(p, "m")  # matches — no error


def test_verify_model_mismatch_raises(tmp_path: Path, monkeypatch):
    from core import security

    pin_file = tmp_path / "pins.yaml"
    monkeypatch.setattr(security, "_model_hashes_path", lambda: pin_file)
    p = tmp_path / "x.bin"
    p.write_bytes(b"foo")
    verify_model(p, "m")  # pins sha256(b"foo")
    p.write_bytes(b"bar")  # file swapped on disk
    with pytest.raises(ValueError, match="SHA256 changed"):
        verify_model(p, "m")
