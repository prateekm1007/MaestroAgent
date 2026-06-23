"""Example plugin: a simple web-search tool.

Drop a file like this into backend/plugins/ to add a new tool. The
loader picks it up automatically at startup.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

from maestro_plugins.registry import PluginEntry


async def web_search_tool(args: dict[str, Any]) -> dict[str, Any]:
    """Search the web for a query. Returns top results."""
    query = args.get("query", "")
    if not query:
        return {"ok": False, "error": "missing 'query'"}
    # In production this would call a real search API (Tavily, Serper, etc.)
    # For demo purposes, we return a stub.
    return {
        "ok": True,
        "query": query,
        "results": [
            {"title": "Stub result 1", "url": "https://example.com/1", "snippet": "..."},
            {"title": "Stub result 2", "url": "https://example.com/2", "snippet": "..."},
        ],
        "note": "This is a stub. Replace with a real search API call.",
    }


web_search_tool.kind = "tool"  # type: ignore[attr-defined]
web_search_tool.description = "Search the web for a query"  # type: ignore[attr-defined]
web_search_tool.version = "0.1.0"  # type: ignore[attr-defined]


# Register via PLUGIN_ENTRIES (the loader picks this up).
PLUGIN_ENTRIES = [
    PluginEntry(
        name="web_search",
        kind="tool",
        factory=web_search_tool,
        description="Search the web for a query",
        version="0.1.0",
    ),
]
