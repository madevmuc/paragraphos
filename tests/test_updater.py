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


def test_check_for_update_uses_configured_repo(monkeypatch):
    from core import updater
    calls = []
    class FakeResp:
        status_code = 200
        def json(self): return {"tag_name": "v1.1.0", "html_url": "x"}
    def fake_get(url, **kw):
        calls.append(url)
        return FakeResp()

    class FakeClient:
        def get(self, url, **kw):
            return fake_get(url, **kw)

    monkeypatch.setattr(updater, "get_client", lambda: FakeClient())

    import threading
    notified = threading.Event()
    updater.check_for_update(
        local_version="1.0.0",
        on_update_available=lambda t, u: notified.set(),
        repo="alice/paragraphos-fork",
        timeout=1.0,
    )
    notified.wait(timeout=2.0)
    assert notified.is_set()
    assert len(calls) == 1
    assert any("alice/paragraphos-fork" in u for u in calls)
