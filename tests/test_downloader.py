from pathlib import Path

import httpx
import pytest
import respx

from core.downloader import download_mp3


@respx.mock
def test_download_fresh_file(tmp_path: Path):
    data = b"\x00" * 2048
    respx.head("https://x.test/a.mp3").respond(
        200,
        headers={"content-length": str(len(data))},
    )
    respx.get("https://x.test/a.mp3").respond(
        200,
        content=data,
        headers={"content-length": str(len(data))},
    )
    dest = tmp_path / "a.mp3"
    result = download_mp3("https://x.test/a.mp3", dest)
    assert result.bytes_written == 2048
    assert result.skipped is False
    assert dest.read_bytes() == data


@respx.mock
def test_download_skips_complete_file(tmp_path: Path):
    data = b"\x00" * 2048
    dest = tmp_path / "a.mp3"
    dest.write_bytes(data)
    respx.head("https://x.test/a.mp3").respond(
        200,
        headers={"content-length": str(len(data))},
    )
    result = download_mp3("https://x.test/a.mp3", dest)
    assert result.skipped is True
    assert result.bytes_written == 0


@respx.mock
def test_download_partial_is_overwritten(tmp_path: Path):
    full = b"\x00" * 2048
    dest = tmp_path / "a.mp3"
    dest.write_bytes(b"\x00" * 1000)
    respx.head("https://x.test/a.mp3").respond(
        200,
        headers={"content-length": str(len(full))},
    )
    respx.get("https://x.test/a.mp3").respond(
        200,
        content=full,
        headers={"content-length": str(len(full))},
    )
    result = download_mp3("https://x.test/a.mp3", dest)
    assert result.skipped is False
    assert dest.stat().st_size == 2048


@respx.mock
def test_download_retries_on_5xx_then_succeeds(tmp_path):
    from pathlib import Path

    calls = {"n": 0}

    def head_resp(request):
        return httpx.Response(200, headers={"content-length": "1024"})

    def get_resp(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"\x00" * 1024, headers={"content-length": "1024"})

    respx.head("https://x.test/a.mp3").mock(side_effect=head_resp)
    respx.get("https://x.test/a.mp3").mock(side_effect=get_resp)
    dest = tmp_path / "a.mp3"
    result = download_mp3("https://x.test/a.mp3", dest, _sleep=lambda _: None)
    assert result.bytes_written == 1024
    assert calls["n"] == 3


@respx.mock
def test_download_does_not_retry_on_404(tmp_path):
    import httpx
    import pytest

    calls = {"n": 0}
    respx.head("https://x.test/gone.mp3").mock(
        side_effect=lambda r: calls.__setitem__("n", calls["n"] + 1) or httpx.Response(404)
    )
    respx.get("https://x.test/gone.mp3").mock(
        side_effect=lambda r: calls.__setitem__("n", calls["n"] + 1) or httpx.Response(404)
    )
    with pytest.raises(httpx.HTTPStatusError):
        download_mp3("https://x.test/gone.mp3", tmp_path / "a.mp3", _sleep=lambda _: None)
    # Single GET attempt, no retry on 4xx. HEAD may fire once.
    assert calls["n"] <= 2


@respx.mock
def test_download_exhausts_retries_then_raises(tmp_path):
    import httpx
    import pytest

    respx.head("https://x.test/flaky.mp3").mock(
        side_effect=lambda r: httpx.Response(200, headers={"content-length": "100"})
    )
    respx.get("https://x.test/flaky.mp3").mock(side_effect=lambda r: httpx.Response(502))
    slept = []
    with pytest.raises(httpx.HTTPStatusError):
        download_mp3(
            "https://x.test/flaky.mp3", tmp_path / "a.mp3", _sleep=lambda s: slept.append(s)
        )
    # Three delays attempted (1, 5, 20) — retries ran.
    assert len(slept) == 3
    assert slept == [1.0, 5.0, 20.0]
