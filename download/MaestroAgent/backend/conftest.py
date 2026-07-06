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

CRITICAL-02 fix: added pytest markers for test suite split + autouse
fixture to reset OEM state between tests (prevents state pollution).
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

# CRITICAL-02 fix: autouse fixture to reset OEM state between tests.
# The #1 cause of test failures was state pollution: test A ingests
# signals, test B sees them. This fixture clears the singleton between
# every test, ensuring hermetic isolation.
import pytest

@pytest.fixture(autouse=True)
def _reset_oem_state():
    """Reset OEM state before each test to prevent cross-test contamination."""
    # Clean up BEFORE the test
    try:
        from maestro_api.oem_state import OEMStateRegistry, oem_state
        OEMStateRegistry.clear()
        if oem_state and hasattr(oem_state, "_initialized"):
            oem_state._initialized = False
            oem_state.engine = None
            oem_state.signals = []
            oem_state._demo_seeded = False
            oem_state._oem_store = None
            oem_state._last_background_loop_result = None
    except Exception:
        pass  # During early test collection, imports may not be ready yet

    yield  # Test runs here

    # Clean up AFTER the test (in case the test left state behind)
    try:
        from maestro_api.oem_state import OEMStateRegistry, oem_state
        OEMStateRegistry.clear()
        if oem_state and hasattr(oem_state, "_initialized"):
            oem_state._initialized = False
            oem_state.engine = None
            oem_state.signals = []
            oem_state._demo_seeded = False
    except Exception:
        pass
