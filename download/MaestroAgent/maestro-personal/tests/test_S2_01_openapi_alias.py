"""S2-1-OPENAPI journey gate — /openapi.json alias must work (401 unauth, 200 with Bearer).

Auditor reported /api/openapi.json returns 404 in production. Root cause:
auditors conventionally hit /openapi.json (FastAPI default) which was
disabled. Fix: stacked decorator — ONE handler at BOTH /api/openapi.json
and /openapi.json, same admin-OR-user Bearer auth.

This is a JOURNEY gate (P35) — it drives the REAL app via FastAPI
TestClient (full middleware + auth stack) and asserts at the product
surface. It does NOT inspect the handler return value; it asserts the
HTTP behavior.

P40: production reliability is a trust property — 404 on a conventional
    path is a trust failure.
P41: single source of truth — the alias must NOT be a second handler,
    it must be the same function object (zero logic duplication).

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python tests/test_S2_01_openapi_alias.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.setdefault("ENV", "dev")
# Load .env.local if present (for OPENROUTER_API_KEY + MAESTRO_PERSONAL_TOKEN)
_env_local = Path("/home/z/my-project/.env.local")
if _env_local.exists():
    for line in _env_local.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@pytest.fixture(scope="module")
def app_client():
    """Spin up the real FastAPI app via TestClient (no mocking)."""
    from fastapi.testclient import TestClient
    from maestro_personal_shell.api import app
    with TestClient(app) as c:
        yield c


def _admin_token() -> str:
    """Read the admin token (MAESTRO_PERSONAL_TOKEN)."""
    return os.environ.get("MAESTRO_PERSONAL_TOKEN", "maestro-demo")


def test_openapi_alias_path_unauth_returns_401_not_404(app_client):
    """FA2 + P40: /openapi.json (no auth) MUST return 401, never 404."""
    resp = app_client.get("/openapi.json")
    assert resp.status_code != 404, (
        "P40 violation: /openapi.json returned 404 — auditors hitting "
        "the conventional path get a trust-breaking 404. Expected 401."
    )
    assert resp.status_code == 401, (
        f"Expected 401 for unauth /openapi.json, got {resp.status_code}"
    )


def test_openapi_canonical_path_unauth_returns_401_not_404(app_client):
    """FA2 + P40: /api/openapi.json (no auth) MUST return 401, never 404."""
    resp = app_client.get("/api/openapi.json")
    assert resp.status_code != 404, "P40 violation: /api/openapi.json returned 404"
    assert resp.status_code == 401


def test_openapi_alias_with_admin_token_returns_200_and_spec(app_client):
    """Admin token (MAESTRO_PERSONAL_TOKEN) MUST return 200 + JSON spec at /openapi.json."""
    resp = app_client.get(
        "/openapi.json",
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    assert resp.headers.get("content-type", "").startswith("application/json"), (
        f"Expected JSON content-type, got {resp.headers.get('content-type')}"
    )
    body = resp.json()
    assert "openapi" in body, "Spec missing 'openapi' key"
    assert "paths" in body, "Spec missing 'paths' key"
    assert body["openapi"].startswith("3."), f"Expected OpenAPI 3.x, got {body['openapi']}"


def test_openapi_canonical_with_admin_token_returns_200_and_spec(app_client):
    """Same admin token MUST return 200 + JSON spec at /api/openapi.json (canonical)."""
    resp = app_client.get(
        "/api/openapi.json",
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "openapi" in body
    assert "paths" in body


def test_alias_and_canonical_return_byte_identical_spec(app_client):
    """P41 anti-drift: the alias and canonical paths MUST return the same spec body."""
    headers = {"Authorization": f"Bearer {_admin_token()}"}
    alias = app_client.get("/openapi.json", headers=headers).json()
    canon = app_client.get("/api/openapi.json", headers=headers).json()
    assert alias == canon, (
        "P41 violation: /openapi.json and /api/openapi.json returned "
        "different spec bodies — the alias must be the SAME handler, "
        "not a copy. Use a stacked @app.get decorator."
    )


def test_root_advertises_contract_paths(app_client):
    """The / service descriptor MUST advertise the contract paths for auditor discovery."""
    resp = app_client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert "contract" in body, (
        "Root / missing 'contract' field — auditors must discover the "
        "OpenAPI paths from /, not from documentation."
    )
    contract = body["contract"]
    assert "canonical" in contract
    assert "aliases" in contract
    assert "/api/openapi.json" == contract["canonical"]
    assert "/openapi.json" in contract["aliases"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
