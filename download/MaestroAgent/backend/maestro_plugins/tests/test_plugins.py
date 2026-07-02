"""Smoke tests for maestro_plugins — discovery + built-in tools."""

from __future__ import annotations

import asyncio

import pytest

from maestro_plugins.builtin_tools import shell_tool
from maestro_plugins.registry import PluginEntry, PluginRegistry


def test_registry_ships_with_builtins() -> None:
    reg = PluginRegistry()
    assert any("shell" in k for k in reg.list())


def test_registry_get_unknown_raises() -> None:
    reg = PluginRegistry()
    with pytest.raises(KeyError):
        reg.get("tool", "never")


def test_registry_register_and_get() -> None:
    reg = PluginRegistry()
    reg.register(PluginEntry(name="x", kind="tool", factory=lambda: None))
    assert reg.get("tool", "x").name == "x"


def test_shell_tool_has_metadata() -> None:
    tool = shell_tool()
    assert callable(tool)
    assert asyncio.iscoroutinefunction(tool)
    assert getattr(tool, "kind", None) == "tool"


async def test_shell_tool_without_ctx_returns_ok_false() -> None:
    """Principle 6: missing ctx must return ok=False, not raise."""
    result = await shell_tool()({"command": "echo hi"})
    assert result["ok"] is False


async def test_shell_tool_runs_locally_with_sandbox_disabled() -> None:
    from maestro_core.context import RunConfig, RunContext
    from maestro_core.streaming import EventBus

    cfg = RunConfig(run_id="r1", template="t", goal="g", sandbox_enabled=False)
    ctx = RunContext(
        config=cfg, llm=None, memory=None, checkpoints=None,  # type: ignore[arg-type]
        events=EventBus(), verifiers=None, plugins=None,  # type: ignore[arg-type]
    )
    result = await shell_tool()({"__ctx": ctx, "command": "echo hello_plugins", "cwd": "/tmp", "timeout": 5})
    assert result["ok"] is True
    assert "hello_plugins" in result["stdout"]
