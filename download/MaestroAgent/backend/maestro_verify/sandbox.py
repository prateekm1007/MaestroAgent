"""Sandbox — Docker-sandboxed command execution.

Tool calls and test runs execute inside a Docker container with:

- Read-only root filesystem (only /workspace is writable).
- No network by default (configurable per-call).
- CPU/memory limits.
- A per-run workspace volume mounted at /workspace.

If Docker is not available, we fall back to local execution with a
loud warning. This fallback is for dev only — production must use the
sandbox.

The protocol
------------
1. The engine calls `run_in_sandbox(ctx, command, cwd, timeout)`.
2. We look up the sandbox container for this run (started lazily).
3. We exec the command, capture stdout/stderr/exit_code, and return.
4. On timeout, we kill the process and return a TIMEOUT result.

For v0.1, the container is a long-lived per-run container. v0.2 will
introduce per-call ephemeral containers for stronger isolation.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maestro_core.context import RunContext

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0


# Per-run container cache: run_id -> container_id
_containers: dict[str, str] = {}


async def run_in_sandbox(
    ctx: "RunContext",
    command: str,
    cwd: str = "/workspace",
    timeout: int = 120,
    network: str | None = None,
) -> SandboxResult:
    """Run a command in the sandbox. Falls back to local exec if Docker is missing."""
    if not ctx.config.sandbox_enabled:
        return await _run_local(command, cwd, timeout)

    try:
        return await _run_docker(ctx, command, cwd, timeout, network)
    except Exception as exc:
        logger.warning(
            "Sandbox execution failed (%s); falling back to local exec. "
            "This is unsafe for untrusted workflows.", exc
        )
        return await _run_local(command, cwd, timeout)


async def _run_docker(
    ctx: "RunContext",
    command: str,
    cwd: str,
    timeout: int,
    network: str | None,
) -> SandboxResult:
    """Run inside a Docker container."""
    import time

    container_id = await _ensure_container(ctx, network)

    # Build the docker exec command.
    exec_cmd = [
        "docker", "exec",
        "-w", cwd,
        container_id,
        "sh", "-c", command,
    ]

    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *exec_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return SandboxResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=time.time() - start,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=f"timeout after {timeout}s",
                timed_out=True,
                duration_seconds=time.time() - start,
            )
    except Exception as exc:
        raise RuntimeError(f"docker exec failed: {exc}") from exc


async def _ensure_container(ctx: "RunContext", network: str | None) -> str:
    """Lazily start a per-run sandbox container."""
    if ctx.config.run_id in _containers:
        return _containers[ctx.config.run_id]

    # Build the docker run command. The container stays alive (sleep infinity)
    # so we can exec multiple commands into it.
    workspace = ctx.config.env.get("WORKSPACE", "/tmp/maestro_workspace")
    args = [
        "docker", "run", "-d",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=64m",
        "-v", f"{workspace}:/workspace",
        "--memory", "1g",
        "--cpus", "1.0",
        "--user", "nobody",
    ]
    if network is None:
        args.extend(["--network", "none"])
    else:
        args.extend(["--network", network])
    args.extend([ctx.config.sandbox_image, "sleep", "infinity"])

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to start sandbox container: {stderr.decode('utf-8', errors='replace')}"
        )
    container_id = stdout.decode().strip()
    _containers[ctx.config.run_id] = container_id
    return container_id


async def _run_local(command: str, cwd: str, timeout: int) -> SandboxResult:
    """Fallback: run locally (DEV ONLY)."""
    import time
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=cwd if cwd != "/workspace" else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return SandboxResult(
                exit_code=proc.returncode or 0,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
                duration_seconds=time.time() - start,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return SandboxResult(
                exit_code=-1,
                stdout="",
                stderr=f"timeout after {timeout}s",
                timed_out=True,
                duration_seconds=time.time() - start,
            )
    except Exception as exc:
        return SandboxResult(
            exit_code=-1,
            stdout="",
            stderr=f"local exec failed: {exc}",
            duration_seconds=time.time() - start,
        )


async def cleanup_run(ctx: "RunContext") -> None:
    """Remove the sandbox container for a run."""
    cid = _containers.pop(ctx.config.run_id, None)
    if cid is None:
        return
    proc = await asyncio.create_subprocess_exec(
        "docker", "rm", "-f", cid,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
