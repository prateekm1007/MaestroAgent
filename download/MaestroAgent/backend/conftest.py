"""Root-level conftest — sets environment variables BEFORE any test collection.

This is the #1 fix for the 415 test failures found by the external audit.
The issue: test files that create their own client fixtures (test_oem_routes,
test_oem_pure_renderer, test_interaction_audit, etc.) call create_app()
without setting MAESTRO_LOCAL_DEV=true. Auth defaults to ON, and every
request returns 401 Unauthorized.

The fix: set MAESTRO_LOCAL_DEV=true at the root conftest level, BEFORE
any test imports or fixture evaluation. This ensures create_app() always
sees the right environment, regardless of which test file runs first.

This file is loaded by pytest BEFORE any test module is imported.
"""
import os

# Set test environment variables IMMEDIATELY — before any imports
os.environ["MAESTRO_LOCAL_DEV"] = "true"
os.environ["MAESTRO_DEMO_SEED"] = "true"
os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
os.environ.setdefault("MAESTRO_RATE_LIMIT_RPM", "10000")

# Set the app dir so create_app() can find app.html
import pathlib
_app_dir = str(pathlib.Path(__file__).resolve().parent.parent)
os.environ.setdefault("MAESTRO_APP_DIR", _app_dir)
