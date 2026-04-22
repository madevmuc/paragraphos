from unittest.mock import patch

from core.compat import CompatStatus, check_compat


def _patch(arch="arm64", mac=("13.4.0", ("", "", ""), ""), mem_gb=16, free_gb=20):
    return patch.multiple(
        "core.compat",
        _machine=lambda: arch,
        _mac_ver=lambda: mac,
        _total_memory_gb=lambda: mem_gb,
        _free_disk_gb=lambda: free_gb,
    )


def test_apple_silicon_modern_os_is_ok():
    with _patch():
        s = check_compat()
    assert s.all_blocking_ok and not s.advisories


def test_intel_is_blocked():
    with _patch(arch="x86_64"):
        s = check_compat()
    assert not s.all_blocking_ok
    assert "Apple Silicon" in s.blocking_reasons[0]


def test_old_macos_is_blocked():
    with _patch(mac=("12.6.0", ("", "", ""), "")):
        s = check_compat()
    assert not s.all_blocking_ok
    assert "macOS 13" in s.blocking_reasons[0]


def test_low_ram_is_advisory_not_blocking():
    with _patch(mem_gb=6):
        s = check_compat()
    assert s.all_blocking_ok
    assert any("RAM" in a for a in s.advisories)


def test_low_disk_is_advisory_not_blocking():
    with _patch(free_gb=2):
        s = check_compat()
    assert s.all_blocking_ok
    assert any("disk" in a.lower() for a in s.advisories)
