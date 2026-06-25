"""Plugin registry — discovers, validates, and exposes plugins."""

from __future__ import annotations

import importlib
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PluginEntry:
    """A registered plugin."""

    name: str
    kind: str  # "agent" | "tool" | "loop" | "verifier" | "memory_backend"
    factory: Any  # callable that produces the instance
    description: str = ""
    version: str = "0.0.0"


class PluginRegistry:
    """Discovers and stores plugins."""

    def __init__(self) -> None:
        self._entries: dict[str, PluginEntry] = {}
        # Built-in tools always available.
        self._register_builtins()

    def register(self, entry: PluginEntry) -> None:
        self._entries[f"{entry.kind}:{entry.name}"] = entry

    def get(self, kind: str, name: str) -> PluginEntry:
        key = f"{kind}:{name}"
        if key not in self._entries:
            raise KeyError(f"Unknown plugin: {key}")
        return self._entries[key]

    def list(self) -> list[str]:
        return sorted(self._entries.keys())

    def list_detailed(self) -> list[dict[str, Any]]:
        return [
            {
                "name": e.name,
                "kind": e.kind,
                "description": e.description,
                "version": e.version,
            }
            for e in self._entries.values()
        ]

    def discover(self) -> None:
        """Discover plugins from entry points + the plugins directory."""
        # 1. Entry-point plugins (installed packages).
        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            # Python 3.10+ may return SelectableGroups.
            if hasattr(eps, "select"):
                plugin_eps = eps.select(group="maestro.plugins")
            else:  # pragma: no cover
                plugin_eps = eps.get("maestro.plugins", [])
            for ep in plugin_eps:
                try:
                    factory = ep.load()
                    self.register(
                        PluginEntry(
                            name=ep.name,
                            kind=getattr(factory, "kind", "tool"),
                            factory=factory,
                            description=getattr(factory, "description", ""),
                            version=getattr(factory, "version", "0.0.0"),
                        )
                    )
                except Exception as exc:
                    logger.warning("Failed to load plugin %s: %s", ep.name, exc)
        except Exception as exc:
            logger.debug("No entry-point plugins discovered: %s", exc)

        # 2. Filesystem plugins from backend/plugins/.
        from maestro_plugins.loader import discover_plugins
        for entry in discover_plugins():
            self.register(entry)

    def _register_builtins(self) -> None:
        """Register built-in tools that ship with MaestroAgent."""
        from maestro_plugins.builtin_tools import (
            shell_tool,
            git_status_tool,
            file_read_tool,
            file_write_tool,
            http_get_tool,
        )

        for name, factory, desc in [
            ("shell", shell_tool, "Run a shell command in the sandbox"),
            ("git_status", git_status_tool, "Get git status of the workspace"),
            ("file_read", file_read_tool, "Read a file from the workspace"),
            ("file_write", file_write_tool, "Write a file to the workspace"),
            ("http_get", http_get_tool, "HTTP GET a URL (egress allowlist applies)"),
        ]:
            self.register(
                PluginEntry(
                    name=name,
                    kind="tool",
                    factory=factory,
                    description=desc,
                    version="0.1.0",
                )
            )
