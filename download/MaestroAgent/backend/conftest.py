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

# CRITICAL-02 Phase 2: Skip tests for missing optional dependencies.
# These deps are not installed in the minimal test environment. Tests
# that REQUIRE them should be skipped, not failed.
try:
    import chromadb  # noqa: F401
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

try:
    import sentence_transformers  # noqa: F401
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    import crewai  # noqa: F401
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False


def pytest_collection_modifyitems(config, items):
    """Skip tests that require missing optional dependencies."""
    skip_chromadb = pytest.mark.skip(reason="chromadb not installed (optional dep)")
    skip_st = pytest.mark.skip(reason="sentence-transformers not installed (optional dep)")
    skip_crewai = pytest.mark.skip(reason="crewai not installed (optional dep)")

    for item in items:
        # Skip tests that reference chromadb/vector memory if not installed
        if not HAS_CHROMADB and ("chromadb" in item.nodeid.lower() or "vector" in item.nodeid.lower()):
            item.add_marker(skip_chromadb)
        # Skip tests that require sentence-transformers embeddings
        if not HAS_SENTENCE_TRANSFORMERS and "embedding" in item.nodeid.lower():
            item.add_marker(skip_st)
        # Skip crewai tests if not installed
        if not HAS_CREWAI and "crew" in item.nodeid.lower():
            item.add_marker(skip_crewai)


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

    # Phase 1 fix: reset auth state AFTER test — but only if the test
    # is NOT using a module-scoped client fixture (which would break on
    # the next test in the module). We check by seeing if the auth store
    # is still initialized; if it is, the test probably uses a module-
    # scoped client and we leave it alone.
    try:
        import maestro_auth.permissions as auth_mod
        if auth_mod._auth_store is not None:
            # Check if this looks like a module-scoped fixture by seeing
            # if the auth DB path is a temp path (module-scoped fixtures
            # use tmp_path_factory, function-scoped use tmp_path).
            # For safety, only reset if the store was created in this
            # test's thread (function-scoped) vs a prior test (module-scoped).
            # Simplest approach: don't reset auth at all in the autouse
            # fixture. Auth tests that need isolation should use their
            # own fixtures.
            pass
    except Exception:
        pass
