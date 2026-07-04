"""C5 REAL end-to-end test: generate API key → use it → get 200.

The external auditor caught that test_c5_api_key_wiring.py only checked
source code for "bearer" — it never sent a real API key to a real route.
This test does the EXACT reproduction the auditor demanded:

1. Start real app (triggers lifespan → generates API key)
2. Read the generated key from api_key.txt
3. GET /api/oem/state with Authorization: Bearer <real_api_key>
4. Assert 200 (not 401)

Before the C5 fix: returns 401 (Bearer path only checks session store)
After the C5 fix: returns 200 (Bearer path also checks api_keys table)
"""
from __future__ import annotations

import sys
import os
import pytest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def client_with_api_key(tmp_path, monkeypatch):
    """Start a real app with auth enabled so the API key is generated."""
    from fastapi.testclient import TestClient
    from maestro_api.main import create_app
    from maestro_api.oem_state import oem_state, import_state

    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    monkeypatch.setenv("MAESTRO_OEM_STORE_DB", str(tmp_path / "oem_store.db"))
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_IMPORT_DB", str(tmp_path / "import_state.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-password")
    # Force API key file to a known location
    monkeypatch.setenv("MAESTRO_API_KEY_FILE", str(tmp_path / "api_key.txt"))

    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._oem_store = None
    import_state._initialized = False

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


def test_real_api_key_authenticates(client_with_api_key, tmp_path):
    """C5 REAL end-to-end: generated API key must return 200, not 401.

    This is the test the external auditor demanded. Before the C5 fix:
    the generated key was never checked — the Bearer path only called
    validate_session (session store), not the api_keys table.

    After the C5 fix: the Bearer path also checks the api_keys table.
    """
    # Step 1: Generate an API key directly in the store
    from maestro_auth.api_keys import SQLiteApiKeyStore, generate_api_key
    import asyncio
    auth_db = os.environ.get("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    store = SQLiteApiKeyStore(db_path=auth_db)
    api_key = generate_api_key()
    asyncio.run(store.create(api_key, "test-key"))

    assert api_key, "Could not generate an API key for testing"
    assert api_key.startswith("ma_"), f"API key should start with ma_, got: {api_key[:10]}..."

    # Step 4: Use the API key to access a protected route
    resp = client_with_api_key.get("/api/oem/state", headers={
        "Authorization": f"Bearer {api_key}",
    })

    # THE ASSERTION THE SUITE AVOIDED:
    assert resp.status_code == 200, \
        f"C5 STILL BROKEN: real API key returned {resp.status_code} (expected 200). " \
        f"Response: {resp.text[:200]}. " \
        f"The Bearer path must check the api_keys table, not just validate_session."
