"""Shared test fixtures for E2E, tenant, and performance tests.

Round 71: Single session-scoped client fixture shared across all test modules.
Prevents prometheus_client duplicate registry errors when running multiple
test files in the same session.
"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    """Create a SINGLE test client for the entire test session.

    Must be session-scoped because:
    1. prometheus_client CollectorRegistry cannot be registered twice
    2. OEM state is an in-memory singleton
    3. The demo seed is deterministic
    """
    os.environ["MAESTRO_LOCAL_DEV"] = "true"
    os.environ["MAESTRO_DEMO_SEED"] = "true"
    os.environ["MAESTRO_APP_DIR"] = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    from maestro_api.main import create_app
    app = create_app()
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
