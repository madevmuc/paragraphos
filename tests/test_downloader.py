from pathlib import Path

import respx

from core.downloader import download_mp3


@respx.mock
def test_download_fresh_file(tmp_path: Path):
    data = b"\x00" * 2048
    respx.head("https://x.test/a.mp3").respond(
        200, headers={"content-length": str(len(data))},
    )
    respx.get("https://x.test/a.mp3").respond(
        200, content=data, headers={"content-length": str(len(data))},
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
        200, headers={"content-length": str(len(data))},
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
        200, headers={"content-length": str(len(full))},
    )
    respx.get("https://x.test/a.mp3").respond(
        200, content=full, headers={"content-length": str(len(full))},
    )
    result = download_mp3("https://x.test/a.mp3", dest)
    assert result.skipped is False
    assert dest.stat().st_size == 2048
