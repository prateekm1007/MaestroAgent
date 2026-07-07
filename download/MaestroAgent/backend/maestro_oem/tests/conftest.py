"""Shared test fixtures for maestro_oem/tests/.

RC3 fix: re-initialize oem_state before each test that uses a module-scoped
client fixture. The root conftest's autouse fixture clears oem_state.signals
between tests, but module-scoped client fixtures build the app once (with
demo seed loaded). Without re-initialization, the next test's request reads
empty state.

This conftest provides a function-scoped autouse fixture that re-initializes
oem_state before each test. Tests that want EMPTY state set MAESTRO_DEMO_SEED=false
in their own fixture, which causes initialize() to skip demo seeding.
"""
import pytest


@pytest.fixture(autouse=True)
def _reinit_oem_state():
    """RC3 fix: re-initialize oem_state before each test.

    This ensures module-scoped client fixtures always see seeded state,
    even after the root conftest's autouse fixture clears oem_state.signals.
    """
    try:
        from maestro_api.oem_state import oem_state
        oem_state._initialized = False
        oem_state.signals = []
        oem_state._demo_seeded = False
        try:
            oem_state.initialize()
        except Exception:
            pass  # Tests that want empty state set MAESTRO_DEMO_SEED=false
    except Exception:
        pass  # During early collection
    yield
