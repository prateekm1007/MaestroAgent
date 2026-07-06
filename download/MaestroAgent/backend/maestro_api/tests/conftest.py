"""Shared test fixtures for E2E, tenant, and performance tests.

Round 71: Single session-scoped client fixture shared across all test modules.
Prevents prometheus_client duplicate registry errors when running multiple
test files in the same session.
"""
import os
import tempfile
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    """Create a SINGLE FastAPI app for the entire test session.

    Must be session-scoped because:
    1. prometheus_client CollectorRegistry cannot be registered twice
    2. OEM state is an in-memory singleton
    3. create_app() has startup side effects that accumulate
    """
    os.environ.setdefault("MAESTRO_LOCAL_DEV", "true")
    os.environ.setdefault("MAESTRO_DEMO_SEED", "true")
    os.environ.setdefault("MAESTRO_APP_DIR", os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    # C6 fix: isolate OEMStore DB to a temp path per test session so the
    # C6 persistence fix doesn't leak state across test runs. Without this,
    # the demo seed persists to oem_store.db, and subsequent test runs load
    # the stale state instead of demo-seeding fresh → test_state_matches_seed_data
    # fails with "got 0 signals".
    _tmpdir = tempfile.mkdtemp(prefix="maestro_test_oem_store_")
    os.environ["MAESTRO_OEM_STORE_DB"] = os.path.join(_tmpdir, "oem_store.db")
    from maestro_api.main import create_app
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    """Create a SINGLE test client for the entire test session."""
    from maestro_api.oem_state import oem_state
    oem_state.initialize()
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_writeback_store():
    """Clear WriteBackStore before each test to prevent state pollution."""
    try:
        from maestro_oem.writeback import WriteBackStore
        WriteBackStore.clear()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def _reinit_oem_state_for_session_client():
    """RC3 fix: re-initialize oem_state before each test.

    The session-scoped client fixture builds the app once and calls
    oem_state.initialize() once. The root conftest's autouse fixture
    clears oem_state.signals between tests. Without re-initialization,
    the next test's request reads empty state.

    This fixture re-initializes oem_state before each test so the
    session-scoped client always sees seeded state. MAESTRO_DEMO_SEED=true
    ensures demo data is loaded on each initialize() call.
    """
    from maestro_api.oem_state import oem_state
    oem_state._initialized = False
    oem_state.signals = []
    oem_state._demo_seeded = False
    try:
        oem_state.initialize()
    except Exception:
        pass  # Tests that want empty state set MAESTRO_DEMO_SEED=false
    yield
