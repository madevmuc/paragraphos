from core.updater import _parse_semver, is_newer


def test_parse_semver_strips_v_prefix():
    assert _parse_semver("v0.5.0") == (0, 5, 0)
    assert _parse_semver("0.5.0") == (0, 5, 0)


def test_parse_semver_handles_prerelease():
    assert _parse_semver("v1.0.0-beta.2") == (1, 0, 0)


def test_is_newer():
    assert is_newer("v0.5.1", "0.5.0")
    assert is_newer("1.0.0", "0.9.9")
    assert not is_newer("0.5.0", "0.5.0")
    assert not is_newer("0.5.0", "0.5.1")


def test_is_newer_tolerates_extra_metadata():
    assert is_newer("v0.6.0-beta", "0.5.0")
