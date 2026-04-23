"""Regression: ``ShowDetailsDialog._retry_feed_now`` rebuild path.

A user crash (SIGABRT via PyQt6's qFatal-on-slot-exception path)
landed when ``Retry now`` succeeded inside the Show Details dialog.
Root cause: ``_retry_feed_now`` captured ``old =
self._feed_health_container`` AFTER calling ``self._build_feed_health_panel()``,
which itself overwrites ``self._feed_health_container`` to point at a
freshly-created (un-parented) widget. ``old.parentWidget()`` then
returned ``None``, ``.layout()`` raised ``AttributeError``, and
PyQt6's slot proxy aborted the process.

This test reproduces the success path end-to-end with ``build_manifest``
+ ``QMessageBox`` stubbed, and asserts no exception is raised. Without
the fix it raises ``AttributeError``.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from core.models import Settings, Show, Watchlist
from core.state import StateStore
from ui.app_context import AppContext

_app_ref = QApplication.instance() or QApplication([])
_keepalive: list = []


@pytest.fixture
def qapp():
    return _app_ref


def _make_ctx(tmp_path, show: Show) -> AppContext:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings()
    settings.output_root = str(tmp_path / "out")
    watchlist = Watchlist(shows=[show])
    watchlist.save(data_dir / "watchlist.yaml")
    state = StateStore(data_dir / "state.sqlite")
    state.init_schema()
    # Mark this show's feed as failed so the Feed health panel actually
    # renders with content (otherwise _build_feed_health_panel returns
    # an empty hidden container and the bug doesn't trigger).
    state.set_meta(f"feed_health:{show.slug}", "fail")
    state.set_meta(f"feed_fail_category:{show.slug}", "dns")
    state.set_meta(f"feed_fail_message:{show.slug}", "Name or service not known")
    state.set_meta(f"feed_fail_at:{show.slug}", "2026-04-23T10:00:00+00:00")
    state.set_meta(f"feed_fail_count:{show.slug}", "5")
    return AppContext(
        data_dir=data_dir,
        settings=settings,
        watchlist=watchlist,
        state=state,
        library=None,  # type: ignore[arg-type]
    )


def _make_dialog(show: Show, tmp_path):
    from ui.show_details_dialog import ShowDetailsDialog

    ctx = _make_ctx(tmp_path, show)
    dlg = ShowDetailsDialog(ctx, show.slug)
    _keepalive.append(dlg)
    return dlg


def test_retry_feed_now_success_does_not_crash(qapp, tmp_path, monkeypatch):
    """Success path: build_manifest returns, panel is rebuilt in place,
    no AttributeError. Pre-fix this raised because old + new aliased
    the same un-parented widget."""
    show = Show(slug="t", title="T", rss="https://example.com/feed", language="de")
    dlg = _make_dialog(show, tmp_path)

    # Stub out the network call + QMessageBox so the test is hermetic.
    monkeypatch.setattr("core.rss.build_manifest", lambda *_a, **_kw: [])
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: 0))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: 0))

    # Sanity: the original panel exists, has a parent, and lives in the
    # dialog's root layout. (If this assertion ever fails, the test is
    # not exercising the bug; the fix is below.)
    original = dlg._feed_health_container
    assert original is not None
    assert original.parentWidget() is dlg

    # Trigger the success path. Pre-fix: AttributeError on
    # `None.layout()`. Post-fix: succeeds.
    dlg._retry_feed_now()

    # After a successful retry the panel should have been swapped — the
    # new container is empty/hidden because feed_health flipped to 'ok'.
    new = dlg._feed_health_container
    assert new is not None
    assert new is not original  # the swap actually happened
    # The new (empty/hidden) panel is in the same layout slot the old
    # one occupied.
    assert new.parentWidget() is dlg


def test_retry_feed_now_failure_path_does_not_crash(qapp, tmp_path, monkeypatch):
    """Failure path: build_manifest raises. The early-return branch
    must not touch the rebuild block, so it never had the ordering
    bug — but pin the behaviour so a future refactor can't reintroduce
    it."""
    show = Show(slug="t2", title="T2", rss="https://example.com/feed", language="de")
    dlg = _make_dialog(show, tmp_path)

    def _boom(*_a, **_kw):
        raise ConnectionError("Name or service not known")

    monkeypatch.setattr("core.rss.build_manifest", _boom)
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: 0))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: 0))

    dlg._retry_feed_now()

    # State should be re-marked as fail with the categorised detail.
    assert dlg.ctx.state.get_meta(f"feed_health:{show.slug}") == "fail"
    assert dlg.ctx.state.get_meta(f"feed_fail_category:{show.slug}") == "dns"
