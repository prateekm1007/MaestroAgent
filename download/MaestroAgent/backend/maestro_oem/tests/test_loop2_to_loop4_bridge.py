"""Phase 2: Loop 2 → Loop 4 bridge integration test.

P11 fix: MeetingIntelligenceLoop.record_learning() composed a learning
entry but it lived only on the Meeting object — invisible to the
OrganizationalLearningLedger (Loop 4). The ledger.record_meeting_learning()
method existed, the HTTP endpoint existed, but neither was called from
the Loop 2 path. This test verifies the bridge works end-to-end.

P22: this test executes the PRODUCTION PATH (HTTP endpoints), not just
unit tests. It:
1. Creates a meeting (POST /loop2/meeting)
2. Prepares it (POST /loop2/meeting/{id}/prepare)
3. Records occurrence (POST /loop2/meeting/{id}/occur)
4. Records outcome (POST /loop2/meeting/{id}/outcome)
5. Records learning (GET /loop2/meeting/{id}/learning)
6. Verifies the learning entry appears in Loop 4 (GET /loop4/entries)
"""
from __future__ import annotations

import sys
import json
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    from fastapi.testclient import TestClient
    from maestro_api.main import create_app
    from maestro_api.oem_state import oem_state, import_state

    tmp_path = tmp_path_factory.mktemp("loop2to4")
    app_dir = str(Path(__file__).resolve().parents[3])
    os.environ["MAESTRO_APP_DIR"] = app_dir
    os.environ["MAESTRO_LOCAL_DEV"] = "true"
    os.environ["MAESTRO_DEMO_SEED"] = "true"
    os.environ["MAESTRO_OEM_STORE_DB"] = str(tmp_path / "oem_store.db")
    os.environ["MAESTRO_AUTH_DB"] = str(tmp_path / "auth.db")
    os.environ["MAESTRO_IMPORT_DB"] = str(tmp_path / "import_state.db")

    oem_state._initialized = False
    oem_state.engine = None
    oem_state.signals = []
    oem_state._demo_seeded = False
    oem_state._oem_store = None
    import_state._initialized = False

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c


def test_loop2_learning_flows_to_loop4(client):
    """P22: when a meeting completes its lifecycle, the learning entry
    must appear in the Loop 4 organizational learning ledger.

    Before the Phase 2 fix: the learning entry lived only on the Meeting
    object. GET /loop4/entries would NOT include it.

    After the fix: record_learning() bridges to ledger.record_meeting_learning().
    GET /loop4/entries includes the meeting learning entry.
    """
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    # Step 1: Create a meeting
    r = client.post("/api/oem/loop2/meeting", json={
        "title": "Loop2to4 Bridge Test Meeting",
        "entity": "Globex",
        "start": f"{tomorrow}T10:00:00Z",
        "end": f"{tomorrow}T11:00:00Z",
        "attendees": ["ceo@globex.com", "jane@acme.com"],
    })
    assert r.status_code == 200, f"Create meeting failed: {r.text[:200]}"
    meeting_id = r.json().get("meeting_id") or r.json().get("id")
    assert meeting_id, f"No meeting_id in response: {r.json()}"

    # Step 2: Prepare
    r = client.post(f"/api/oem/loop2/meeting/{meeting_id}/prepare", json={})
    assert r.status_code == 200, f"Prepare failed: {r.text[:200]}"

    # Step 3: Record occurrence
    r = client.post(f"/api/oem/loop2/meeting/{meeting_id}/occur", json={
        "topics_discussed": ["SSO delivery", "Q4 renewal"],
        "commitments_made": ["Deliver SSO by 2024-12-15"],
    })
    assert r.status_code == 200, f"Occur failed: {r.text[:200]}"

    # Step 4: Record outcome
    r = client.post(f"/api/oem/loop2/meeting/{meeting_id}/outcome", json={
        "outcome": "commitment_honored",
    })
    assert r.status_code == 200, f"Outcome failed: {r.text[:200]}"

    # Step 5: Record learning (this is where the bridge fires)
    r = client.get(f"/api/oem/loop2/meeting/{meeting_id}/learning")
    assert r.status_code == 200, f"Learning failed: {r.text[:200]}"
    learning_data = r.json()
    learning_entry = learning_data.get("learning_entry", "")
    assert learning_entry, \
        f"Learning entry should be non-empty. Response: {learning_data}"

    # Step 6: Verify the learning entry appears in Loop 4
    r = client.get("/api/oem/loop4/entries")
    assert r.status_code == 200, f"Loop4 entries failed: {r.text[:200]}"
    entries = r.json().get("entries", [])

    # Find the entry from our meeting
    meeting_entries = [
        e for e in entries
        if e.get("source_loop") == "meeting"
        and (e.get("id") == meeting_id or "loop2to4" in (e.get("learning_entry", "") + str(e.get("id", ""))).lower()
             or "globex" in e.get("entity", "").lower()
             or "loop2to4 bridge" in e.get("learning_entry", "").lower())
    ]

    assert len(meeting_entries) > 0, \
        f"Loop 2 → Loop 4 bridge FAILED: meeting learning entry not found in Loop 4. " \
        f"Loop 4 entries: {json.dumps(entries[:3], indent=2)[:500]}"

    entry = meeting_entries[0]
    assert entry.get("source_loop") == "meeting", \
        f"Entry source_loop should be 'meeting'. Got: {entry.get('source_loop')}"
    assert entry.get("learning_entry"), \
        f"Entry should have non-empty learning_entry. Got: {entry}"

    print(f"\n=== Loop 2 → Loop 4 bridge verified ===")
    print(f"  Meeting: {meeting_id}")
    print(f"  Learning entry: {entry.get('learning_entry', '')[:120]}")
    print(f"  Source loop: {entry.get('source_loop')}")
    print(f"  Entity: {entry.get('entity')}")
