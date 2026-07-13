"""
Task 57-a: API contract tests.

Goals:
  1. Regenerate openapi_schema.json from the live FastAPI app and diff
     against the committed schema (drift detection).
  2. Verify the committed schema is valid OpenAPI 3.x.
  3. Verify every endpoint declared in the schema has at least one
     backend test that touches it (coverage check).
  4. Verify the mobile client's hardcoded endpoint list is a SUBSET of
     the OpenAPI schema (no orphan calls).
  5. Verify every request body schema and response schema referenced by
     the OpenAPI is importable (no missing component references).

This is a contract test — it does NOT spin up the server. It loads the
FastAPI app object directly and asks it for `app.openapi()`.

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python tests/test_api_contract.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

# Ensure the src package is importable.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Avoid production-mode stripping of docs/openapi_url during the schema dump.
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.setdefault("ENV", "dev")

COMMITTED_SCHEMA_PATH = REPO_ROOT / "docs" / "openapi_schema.json"
MOBILE_CLIENT_PATH = REPO_ROOT / "mobile" / "src" / "api" / "client.ts"
WEB_CLIENT_PATH = REPO_ROOT / "web" / "src" / "lib" / "maestro-api.ts"


def _load_live_schema():
    """Import the FastAPI app and dump its OpenAPI schema."""
    # The api module is heavy — importing it has side effects (logger, db).
    # That's fine for a contract test; we're verifying the real app.
    from maestro_personal_shell.api import app  # noqa: E402

    return app.openapi()


def _load_committed_schema():
    with open(COMMITTED_SCHEMA_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. Drift detection — committed schema matches the live FastAPI app.
# ---------------------------------------------------------------------------

def test_committed_schema_matches_live_app():
    """The committed openapi_schema.json must match what FastAPI generates.

    If this fails, run `python scripts/dump_openapi.py > docs/openapi_schema.json`
    to refresh, then review the diff before committing.
    """
    live = _load_live_schema()
    committed = _load_committed_schema()

    live_paths = set(live.get("paths", {}).keys())
    committed_paths = set(committed.get("paths", {}).keys())

    added = live_paths - committed_paths
    removed = committed_paths - live_paths

    assert not added, (
        f"Live app has {len(added)} paths not in committed schema: "
        f"{sorted(added)[:10]}. Re-dump the schema."
    )
    assert not removed, (
        f"Committed schema has {len(removed)} paths not in live app: "
        f"{sorted(removed)[:10]}. Re-dump the schema."
    )

    # Spot-check: the schema title/version match.
    assert committed["info"]["title"] == live["info"]["title"]
    assert committed["info"]["version"] == live["info"]["version"]


# ---------------------------------------------------------------------------
# 2. Schema validity — OpenAPI 3.x and JSON dereferences resolve.
# ---------------------------------------------------------------------------

def test_schema_is_openapi_3():
    schema = _load_committed_schema()
    version = schema.get("openapi", "")
    assert version.startswith("3."), f"Expected OpenAPI 3.x, got {version}"


def test_all_schema_references_resolve():
    """Every $ref in the schema must point at a real component."""
    schema = _load_committed_schema()
    components = schema.get("components", {}).get("schemas", {})
    refs_found: set[str] = set()
    refs_missing: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "$ref" and isinstance(v, str):
                    refs_found.add(v)
                else:
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(schema)

    for ref in refs_found:
        # Form: "#/components/schemas/Foo"
        if not ref.startswith("#/components/schemas/"):
            refs_missing.add(ref)
            continue
        name = ref.split("/")[-1]
        if name not in components:
            refs_missing.add(ref)

    assert not refs_missing, (
        f"{len(refs_missing)} schema $ref(s) point at missing components: "
        f"{sorted(refs_missing)[:10]}"
    )


# ---------------------------------------------------------------------------
# 3. Endpoint coverage — every schema path has at least one backend test
#    that mentions it.
# ---------------------------------------------------------------------------

def _scan_tests_for_endpoint_mentions():
    """Return a dict: endpoint_path -> list of test files that mention it.

    For paths with `{param}` placeholders, also accept any test that uses
    the path prefix with a real value (e.g. `/api/copilot/playbooks/foo`
    counts as covering `/api/copilot/playbooks/{playbook_id}`).
    """
    test_dir = REPO_ROOT / "tests"
    mentions: dict[str, list[str]] = {}
    # Pre-load all test file texts.
    test_texts: list[tuple[str, str]] = []
    for test_file in test_dir.glob("test_*.py"):
        try:
            test_texts.append((test_file.name, test_file.read_text()))
        except UnicodeDecodeError:
            continue

    for path in _all_schema_paths():
        # Build a regex that matches the literal path OR the path with
        # {param} placeholders replaced by [^/]+ (and possibly extended
        # with /subpaths for nested resources).
        # First, try the literal path.
        for fname, text in test_texts:
            if path in text:
                mentions.setdefault(path, []).append(fname)
                continue
        if path in mentions:
            continue
        # Fall back to regex matching for templated paths.
        if "{" in path:
            # Replace {param} with [^/]+ and search for the pattern.
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", path)
            for fname, text in test_texts:
                if re.search(pattern, text):
                    mentions.setdefault(path, []).append(fname)
    return mentions


def _all_schema_paths():
    schema = _load_committed_schema()
    return sorted(schema.get("paths", {}).keys())


def test_every_endpoint_has_at_least_one_test():
    """Every path in the OpenAPI schema should appear in at least one test file.

    This is a soft coverage gate — if an endpoint is untested, it's a smell
    but not necessarily a bug. We report them all but only fail if >10% are
    uncovered (avoids noise from admin/health endpoints).
    """
    mentions = _scan_tests_for_endpoint_mentions()
    all_paths = _all_schema_paths()
    uncovered = [p for p in all_paths if p not in mentions]

    # Allow up to 10% uncovered (admin/health/internal endpoints).
    threshold = max(1, len(all_paths) // 10)
    if len(uncovered) > threshold:
        msg = (
            f"{len(uncovered)} of {len(all_paths)} endpoints have ZERO test "
            f"mentions (threshold: {threshold}). Uncovered:\n  "
            + "\n  ".join(sorted(uncovered)[:30])
        )
        pytest.fail(msg)
    else:
        # Just print the uncovered list as a warning.
        if uncovered:
            print(
                f"\n[INFO] {len(uncovered)} endpoints untested (within "
                f"threshold of {threshold}): {sorted(uncovered)}"
            )


# ---------------------------------------------------------------------------
# 4. Mobile + web client subset check — every endpoint the clients call
#    must exist in the OpenAPI schema.
# ---------------------------------------------------------------------------

def _extract_client_endpoints(client_path: Path) -> set[str]:
    """Parse a TypeScript client file and extract endpoint paths.

    Looks for string literals starting with `/api/` (the standard Maestro
    API prefix). Handles both `/api/foo` and template literals like
    `/api/foo/${id}` (collapses the `${...}` to `{...}`).
    """
    if not client_path.exists():
        return set()
    text = client_path.read_text()
    # Match /api/... up to the next quote, backtick, or whitespace.
    raw = re.findall(r"`[^`]*?/api/[^`]*?`|['\"][^'\"]*?/api/[^'\"]*?['\"]", text)
    endpoints: set[str] = set()
    for match in raw:
        # Strip the quote/backtick chars from both ends.
        body = match[1:-1]
        # Collapse ${var} → {var} to match OpenAPI path style.
        body = re.sub(r"\$\{([^}]+)\}", r"{\1}", body)
        # Some template literals have query strings or interpolation past
        # the path — take only up to the first ? or whitespace.
        body = re.split(r"[?\s]", body, 1)[0]
        endpoints.add(body)
    return endpoints


def test_mobile_client_endpoints_exist_in_schema():
    """Every /api/... endpoint the mobile client calls must be in the schema."""
    schema = _load_committed_schema()
    schema_paths = set(schema.get("paths", {}).keys())

    mobile_endpoints = _extract_client_endpoints(MOBILE_CLIENT_PATH)
    # Filter out fragmentary matches like "/api/" alone.
    mobile_endpoints = {e for e in mobile_endpoints if e.count("/") >= 3}

    orphan = sorted(e for e in mobile_endpoints if e not in schema_paths)
    # Allow known dynamic-suffix endpoints that the regex can't fully resolve.
    # Print but don't fail unless there's a clear mismatch.
    if orphan:
        # Check if each orphan is a prefix of some schema path (e.g. /api/connectors/gmail/oauth/callback
        # might appear as /api/connectors/{provider} in the schema).
        true_orphans = []
        for e in orphan:
            # Try matching against schema paths with {param} placeholders.
            matched = False
            for sp in schema_paths:
                # Replace {param} with [^/]+ and check.
                pattern = re.sub(r"\{[^}]+\}", r"[^/]+", sp) + "$"
                if re.match(pattern, e):
                    matched = True
                    break
            if not matched:
                true_orphans.append(e)

        if true_orphans:
            pytest.fail(
                f"Mobile client calls {len(true_orphans)} endpoints NOT in "
                f"OpenAPI schema: {true_orphans}"
            )


def test_web_client_endpoints_exist_in_schema():
    """Every /api/... endpoint the web client calls must be in the schema."""
    schema = _load_committed_schema()
    schema_paths = set(schema.get("paths", {}).keys())

    web_endpoints = _extract_client_endpoints(WEB_CLIENT_PATH)
    web_endpoints = {e for e in web_endpoints if e.count("/") >= 3}

    orphan = sorted(e for e in web_endpoints if e not in schema_paths)
    true_orphans = []
    for e in orphan:
        matched = False
        for sp in schema_paths:
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", sp) + "$"
            if re.match(pattern, e):
                matched = True
                break
        if not matched:
            true_orphans.append(e)

    if true_orphans:
        pytest.fail(
            f"Web client calls {len(true_orphans)} endpoints NOT in "
            f"OpenAPI schema: {true_orphans}"
        )


# ---------------------------------------------------------------------------
# 5. Critical endpoints sanity — the "must-work" set actually exists.
# ---------------------------------------------------------------------------

CRITICAL_ENDPOINTS = [
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/revoke"),
    ("GET", "/api/health"),
    ("POST", "/api/ask"),
    ("GET", "/api/commitments"),
    ("GET", "/api/commitments/the-one"),
    ("GET", "/api/signals"),
    ("GET", "/api/briefing"),
    ("GET", "/api/connectors"),
    ("GET", "/api/llm-status"),
    ("GET", "/api/account/export"),
    ("DELETE", "/api/account"),
    ("GET", "/api/privacy/mode"),
]


def test_critical_endpoints_exist():
    """A short list of must-exist endpoints for the product to function."""
    schema = _load_committed_schema()
    paths = schema.get("paths", {})
    missing = []
    for method, path in CRITICAL_ENDPOINTS:
        if path not in paths:
            missing.append(f"{method} {path}")
            continue
        if method.lower() not in paths[path]:
            missing.append(f"{method} {path} (method missing)")
    assert not missing, (
        f"{len(missing)} critical endpoints missing from schema: {missing}"
    )


if __name__ == "__main__":
    # Allow running as a script for quick diagnostics.
    sys.exit(pytest.main([__file__, "-v"]))
