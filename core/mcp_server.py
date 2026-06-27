"""MCP server — skeleton (roadmap 10.3).

A Model Context Protocol wrapper would let an LLM client drive Paragraphos over
stdio. The **stdio transport** needs the `mcp` package, which isn't added in this
run (escape hatch) — see ``docs/plans/mcp-server-design.md``. What ships here is
the transport-independent core: a tool registry + ``call_tool`` dispatcher that
reuses the localhost API router (``core.api_server.handle_request``), so wiring
a real MCP transport on top is mechanical.
"""

from __future__ import annotations

from core.api_server import handle_request

# Tool name → (description, method, path). Mirrors the JSON API surface.
_TOOLS = {
    "list_shows": ("List all shows in the watchlist.", "GET", "/shows"),
    "queue_status": ("Queue depth + by-status counts.", "GET", "/status"),
    "list_queue": ("List pending episodes in the queue.", "GET", "/queue"),
    "pause_queue": ("Pause the processing queue.", "POST", "/queue/pause"),
    "resume_queue": ("Resume the processing queue.", "POST", "/queue/resume"),
}

# An internal token: dispatch goes straight through the router in-process, so we
# pass a fixed token as both expected + provided (no network, no real auth here).
_LOCAL_TOKEN = "mcp-local"


def list_tools() -> list[dict]:
    """Return MCP-style tool descriptors for the exposed surface."""
    return [{"name": name, "description": desc} for name, (desc, _m, _p) in _TOOLS.items()]


def call_tool(name: str, arguments: dict, ctx) -> dict:
    """Dispatch a tool call to the API router. Raises KeyError for unknown tools."""
    if name not in _TOOLS:
        raise KeyError(f"unknown tool: {name!r}")
    _desc, method, path = _TOOLS[name]
    _status, body = handle_request(method, path, _LOCAL_TOKEN, _LOCAL_TOKEN, ctx)
    return body
