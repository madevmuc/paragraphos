"""MCP server skeleton (10.3) — tool registry + dispatch over the API surface."""

from __future__ import annotations

from core.mcp_server import call_tool, list_tools
from core.models import Settings, Show, Watchlist
from core.state import StateStore


class _Ctx:
    def __init__(self, tmp_path):
        self.watchlist = Watchlist(shows=[Show(slug="sh", title="Show", rss="r")])
        self.state = StateStore(tmp_path / "s.sqlite")
        self.state.init_schema()
        self.settings = Settings()


def test_list_tools_describes_surface():
    tools = list_tools()
    names = {t["name"] for t in tools}
    assert {"list_shows", "queue_status", "pause_queue", "resume_queue"} <= names
    for t in tools:
        assert t["name"] and t["description"]


def test_call_tool_list_shows(tmp_path):
    out = call_tool("list_shows", {}, _Ctx(tmp_path))
    assert out["shows"][0]["slug"] == "sh"


def test_call_tool_pause_resume(tmp_path):
    ctx = _Ctx(tmp_path)
    call_tool("pause_queue", {}, ctx)
    assert ctx.state.get_meta("queue_paused") == "1"
    call_tool("resume_queue", {}, ctx)
    assert ctx.state.get_meta("queue_paused") == "0"


def test_call_unknown_tool_raises(tmp_path):
    import pytest

    with pytest.raises(KeyError):
        call_tool("nope", {}, _Ctx(tmp_path))
