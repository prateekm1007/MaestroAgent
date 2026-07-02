"""Template routes — list available workflow templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request

from maestro_auth.permissions import is_auth_enabled, require_user
from maestro_api.security.policy import set_router_policy, AuthPolicy
def _require_user_if_auth_enabled(request: Request) -> None:
    """Auth gate that respects dev mode. See imports.py for the pattern."""
    if is_auth_enabled():
        require_user(request)


router = APIRouter(dependencies=[Depends(_require_user_if_auth_enabled)])


@router.get("")
async def list_templates() -> list[dict[str, Any]]:
    """List available templates from examples/templates/."""
    templates_dir = Path(__file__).parent.parent.parent / "examples" / "templates"
    if not templates_dir.exists():
        return []
    templates = []
    for p in templates_dir.glob("*.py"):
        if p.name.startswith("_"):
            continue
        name = p.stem
        # Read the first docstring as description (best effort).
        text = p.read_text()
        desc = ""
        if '"""' in text:
            start = text.find('"""') + 3
            end = text.find('"""', start)
            if end > start:
                desc = text[start:end].strip().split("\n")[0]
        templates.append({"name": name, "description": desc, "path": str(p)})
    return templates

# Phase 1: stamp USER auth policy on all routes in this router
set_router_policy(router, AuthPolicy.USER)
