"""Categorisation rules for ``core.feed_errors.categorize``.

These are the buckets surfaced in the Shows-tab pill, the Show-details
'Feed health' panel, and the CLI ``feed-health`` output. The mapping is
load-bearing: rename a category and every persisted ``feed_fail_category``
in users' state.sqlite goes stale, so this test pins the canonical set
plus the dispatch paths.
"""

from __future__ import annotations

import socket

import pytest

from core.feed_errors import (
    DNS,
    FORBIDDEN,
    GONE,
    MALFORMED,
    OTHER,
    REDIRECT_LOOP,
    SERVER,
    SSRF,
    TIMEOUT,
    TLS,
    TOO_LARGE,
    categorize,
    label,
    recommendation,
)
from core.security import UnsafeURLError


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeHTTPStatusError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.response = _FakeResponse(status_code)


def test_ssrf_guard_is_categorised_first():
    """UnsafeURLError is a ValueError subclass; categorize must catch it
    by class before falling through to the ValueError text-match for
    'feed too large'."""
    assert categorize(UnsafeURLError("refused private-network host 'x'")) == SSRF


@pytest.mark.parametrize(
    "status,expected",
    [
        (404, GONE),
        (410, GONE),
        (401, FORBIDDEN),
        (403, FORBIDDEN),
        (500, SERVER),
        (502, SERVER),
        (503, SERVER),
        (504, SERVER),
        (429, SERVER),  # rate limit → server bucket (transient)
        (400, SERVER),
    ],
)
def test_http_status_dispatch(status, expected):
    assert categorize(_FakeHTTPStatusError(status)) == expected


def test_timeout_by_class_name():
    class ReadTimeout(Exception):
        pass

    assert categorize(ReadTimeout("read timed out")) == TIMEOUT


def test_timeout_by_message():
    assert categorize(Exception("operation timeout after 30s")) == TIMEOUT


def test_too_many_redirects():
    class TooManyRedirects(Exception):
        pass

    assert categorize(TooManyRedirects("too many redirects")) == REDIRECT_LOOP


def test_tls_class():
    class SSLError(Exception):
        pass

    assert categorize(SSLError("handshake failed")) == TLS


def test_tls_message():
    assert categorize(Exception("certificate verify failed")) == TLS


def test_dns_gaierror():
    assert categorize(socket.gaierror("nodename nor servname provided")) == DNS


def test_dns_message():
    assert categorize(Exception("Name or service not known")) == DNS


def test_generic_connect_error():
    class ConnectError(Exception):
        pass

    assert categorize(ConnectError("Connection refused")) == DNS


def test_too_large():
    assert categorize(ValueError("feed too large: 80000000 bytes")) == TOO_LARGE


def test_malformed_xml():
    class ParseError(Exception):
        pass

    assert categorize(ParseError("not well-formed")) == MALFORMED


def test_unknown_falls_through_to_other():
    assert categorize(RuntimeError("???")) == OTHER


def test_recommendation_never_blank_for_known_categories():
    for cat in (
        DNS,
        TIMEOUT,
        TLS,
        FORBIDDEN,
        GONE,
        SERVER,
        MALFORMED,
        REDIRECT_LOOP,
        SSRF,
        TOO_LARGE,
        OTHER,
    ):
        rec = recommendation(cat)
        assert rec
        # Must be readable — at least 30 characters.
        assert len(rec) > 30, f"too terse for {cat}: {rec!r}"


def test_recommendation_unknown_category_falls_back_to_other():
    """Old persisted state could carry a category we no longer know
    about. Don't render blank."""
    assert recommendation("not-a-real-category") == recommendation(OTHER)


def test_label_short_enough_for_pill():
    """Pill cell is ~120 px; the label must fit after 'fail · '."""
    for cat in (
        DNS,
        TIMEOUT,
        TLS,
        FORBIDDEN,
        GONE,
        SERVER,
        MALFORMED,
        REDIRECT_LOOP,
        SSRF,
        TOO_LARGE,
        OTHER,
    ):
        assert len(label(cat)) <= 14, f"label too long: {cat} → {label(cat)!r}"
