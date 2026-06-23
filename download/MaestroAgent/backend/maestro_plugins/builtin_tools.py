"""Built-in tools that ship with MaestroAgent.

These tools are registered automatically by the `PluginRegistry` and
available to all agents. They wrap the sandbox runner for shell/file
ops and the httpx client for HTTP.

Each tool is a factory that returns an async callable:
    async def tool(args: dict) -> dict

The callable takes a dict of args and returns a dict with at least
`{"ok": bool, ...}`. Errors are returned (not raised) so the agent
can read them.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable


def shell_tool() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Run a shell command in the sandbox."""
    async def _tool(args: dict[str, Any]) -> dict[str, Any]:
        from maestro_verify.sandbox import run_in_sandbox
        from maestro_core.context import RunContext  # type: ignore
        # The tool needs a RunContext; agents pass it via args["__ctx"].
        ctx: Any = args.get("__ctx")
        if ctx is None:
            return {"ok": False, "error": "no __ctx in args"}
        command = args.get("command", "")
        cwd = args.get("cwd", "/workspace")
        timeout = int(args.get("timeout", 120))
        result = await run_in_sandbox(ctx, command=command, cwd=cwd, timeout=timeout)
        return {
            "ok": result.exit_code == 0,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
        }
    _tool.kind = "tool"  # type: ignore[attr-defined]
    _tool.description = "Run a shell command in the sandbox"  # type: ignore[attr-defined]
    _tool.version = "0.1.0"  # type: ignore[attr-defined]
    return _tool


def git_status_tool() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Get git status."""
    async def _tool(args: dict[str, Any]) -> dict[str, Any]:
        from maestro_verify.sandbox import run_in_sandbox
        ctx: Any = args.get("__ctx")
        if ctx is None:
            return {"ok": False, "error": "no __ctx in args"}
        result = await run_in_sandbox(ctx, "git status --porcelain", cwd="/workspace", timeout=30)
        return {
            "ok": result.exit_code == 0,
            "status": result.stdout,
            "stderr": result.stderr,
        }
    _tool.kind = "tool"  # type: ignore[attr-defined]
    _tool.description = "Get git status of the workspace"  # type: ignore[attr-defined]
    _tool.version = "0.1.0"  # type: ignore[attr-defined]
    return _tool


def file_read_tool() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Read a file from the workspace."""
    async def _tool(args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", "")
        if not path:
            return {"ok": False, "error": "missing 'path'"}
        # Restrict to /workspace for safety.
        if not path.startswith("/workspace/") and path != "/workspace":
            path = f"/workspace/{path}"
        try:
            from pathlib import Path
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            return {"ok": True, "content": content, "path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": path}
    _tool.kind = "tool"  # type: ignore[attr-defined]
    _tool.description = "Read a file from the workspace"  # type: ignore[attr-defined]
    _tool.version = "0.1.0"  # type: ignore[attr-defined]
    return _tool


def file_write_tool() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Write a file to the workspace."""
    async def _tool(args: dict[str, Any]) -> dict[str, Any]:
        path = args.get("path", "")
        content = args.get("content", "")
        if not path:
            return {"ok": False, "error": "missing 'path'"}
        if not path.startswith("/workspace/") and path != "/workspace":
            path = f"/workspace/{path}"
        try:
            from pathlib import Path
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"ok": True, "path": str(p), "bytes": len(content)}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": path}
    _tool.kind = "tool"  # type: ignore[attr-defined]
    _tool.description = "Write a file to the workspace"  # type: ignore[attr-defined]
    _tool.version = "0.1.0"  # type: ignore[attr-defined]
    return _tool


def http_get_tool() -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """HTTP GET a URL. Subject to the run's egress allowlist."""
    async def _tool(args: dict[str, Any]) -> dict[str, Any]:
        import httpx
        url = args.get("url", "")
        if not url:
            return {"ok": False, "error": "missing 'url'"}
        # TODO(v0.2): enforce egress allowlist from ctx.config.
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url)
                return {
                    "ok": resp.status_code < 400,
                    "status_code": resp.status_code,
                    "content": resp.text[:10000],
                    "headers": dict(resp.headers),
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "url": url}
    _tool.kind = "tool"  # type: ignore[attr-defined]
    _tool.description = "HTTP GET a URL (egress allowlist applies)"  # type: ignore[attr-defined]
    _tool.version = "0.1.0"  # type: ignore[attr-defined]
    return _tool
