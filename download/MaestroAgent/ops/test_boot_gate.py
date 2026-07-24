#!/usr/bin/env python3
"""test_boot_gate.py — The boot gate (P35 enforcement).

Auditor (2026-07-24): "A boot gate — a CI step that actually starts the
application (imports every module, registers every router, boots the
server) and asserts it serves /api/health before the deploy is allowed
to proceed. A missing import, a broken router registration, a startup
exception — any of these fails the boot gate in seconds, in CI, instead
of crashing production."

This is the SIMPLEST journey gate: can the app even start? The 2,248-case
classifier gold-set and the 13-case ask-correctness gate both passed while
the backend couldn't boot because of a missing `Header` import. Those gates
import modules in isolation; this gate imports the FULL application and
asserts it boots + serves health.

USAGE:
    python3 ops/test_boot_gate.py
    (exit 0 = app boots + serves health, exit 1 = app fails to start)
"""
from __future__ import annotations

import sys
import os

# Set up the environment like production
os.environ.setdefault("MAESTRO_PERSONAL_ENV", "production")
os.environ.setdefault("MAESTRO_PERSONAL_DB", "/tmp/boot_gate_test.db")

def main():
    print("=" * 60)
    print("BOOT GATE (P35 enforcement)")
    print("Can the full application start + serve /api/health?")
    print("=" * 60)

    errors = []

    # Step 1: Import the main API module — this triggers all router
    # registrations, middleware setup, and lifespan handlers.
    print("\n[1] Importing the full application...")
    try:
        # This imports api.py which imports all routers, registers all
        # middleware, and creates the FastAPI app. If ANY import is broken,
        # ANY router has a bad signature, or ANY middleware fails, this
        # will raise an ImportError or similar.
        from maestro_personal_shell.api import app
        print("  ✓ All modules imported successfully")
        print(f"  ✓ FastAPI app created: {app.title} v{app.version}")
    except Exception as e:
        print(f"  ✗ IMPORT FAILED: {e}")
        errors.append(f"import: {e}")
        # Don't continue — if the app can't be imported, nothing else matters
        print(f"\n❌ BOOT GATE FAILED — the application cannot start")
        print(f"   Root cause: {e}")
        sys.exit(1)

    # Step 2: Verify all routers are registered
    print("\n[2] Verifying router registration...")
    try:
        routes = [r.path for r in app.routes]
        critical_routes = [
            "/api/health",
            "/api/auth/register",
            "/api/auth/login",
            "/api/signals",
            "/api/ask",
            "/api/commitments",
            "/api/connectors",
            "/api/what-changed",
        ]
        for route in critical_routes:
            # Check if the route exists (may be a prefix match)
            found = any(route == r or route.startswith(r.rstrip("/") + "/") or r.startswith(route) for r in routes)
            if found:
                print(f"  ✓ {route}")
            else:
                print(f"  ✗ {route} — NOT FOUND")
                errors.append(f"missing route: {route}")
    except Exception as e:
        print(f"  ✗ Route verification failed: {e}")
        errors.append(f"routes: {e}")

    # Step 3: Boot the app with TestClient and assert /api/health responds
    print("\n[3] Booting app with TestClient + asserting /api/health...")
    try:
        from fastapi.testclient import TestClient
        client = TestClient(app)

        resp = client.get("/api/health")
        if resp.status_code == 200:
            data = resp.json()
            print(f"  ✓ /api/health returned 200")
            print(f"    status={data.get('status')}")
            print(f"    version={data.get('version')}")
            print(f"    commit={data.get('commit','?')[:12]}")
        else:
            print(f"  ✗ /api/health returned {resp.status_code}")
            errors.append(f"health: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  ✗ App boot failed: {e}")
        errors.append(f"boot: {e}")

    # Step 4: Verify a few critical endpoints don't crash on boot
    print("\n[4] Verifying critical endpoints don't crash...")
    try:
        # /api/openapi.json — tests that the OpenAPI schema generation works
        resp = client.get("/api/openapi.json")
        if resp.status_code in (200, 401):
            print(f"  ✓ /api/openapi.json responded (HTTP {resp.status_code})")
        else:
            print(f"  ✗ /api/openapi.json returned {resp.status_code}")
            errors.append(f"openapi: HTTP {resp.status_code}")

        # Root — tests the root handler
        resp = client.get("/")
        if resp.status_code == 200:
            print(f"  ✓ / responded (HTTP {resp.status_code})")
        else:
            print(f"  ✗ / returned {resp.status_code}")
            errors.append(f"root: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  ✗ Endpoint check failed: {e}")
        errors.append(f"endpoints: {e}")

    # Result
    print(f"\n{'='*60}")
    if not errors:
        print("✅ BOOT GATE PASSED — the application starts and serves health")
        print("   All modules imported, all routers registered, /api/health responds 200")
        sys.exit(0)
    else:
        print(f"❌ BOOT GATE FAILED — {len(errors)} error(s):")
        for e in errors:
            print(f"   • {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
