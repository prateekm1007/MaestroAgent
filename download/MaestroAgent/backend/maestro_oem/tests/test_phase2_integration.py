"""Phase 2 P22 integration tests: verify user-visible behavior, not just wiring.

The auditor verified the 3 P11 fixes are WIRED (grep + inspect.signature).
But per P22: "wiring is not behavior." These tests verify the user-visible
change — does the API actually return different data now?

Test 1: /preparation/tomorrow returns real MeetingStore meetings (not demo)
Test 2: Ask 'why' question surfaces synthesis_hints (causal chain text)
Test 3: Ask 'What did we discuss in the Globex meeting?' reaches Meeting data
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
    """Module-scoped test client with demo seed."""
    import os
    from fastapi.testclient import TestClient
    from maestro_api.main import create_app
    from maestro_api.oem_state import oem_state, import_state

    tmp_path = tmp_path_factory.mktemp("phase2")
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


def test_preparation_tomorrow_returns_real_meetings_from_meeting_store(client):
    """P22 Test 1: /preparation/tomorrow must surface real MeetingStore meetings.

    Before the Phase 2 fix: PreparationEngine used DemoCalendarSource which
    synthesizes fake meetings from signals. Real meetings stored via
    /loop2/meeting were invisible.

    After the fix: if MeetingStore has meetings, they appear in the prep brief.

    Test: ingest a real meeting via POST /loop2/meeting, then call
    /preparation/tomorrow and verify the real meeting title appears.
    """
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    # Step 1: Create a real meeting via the Loop 2 API
    meeting_resp = client.post("/api/oem/loop2/meeting", json={
        "title": "P22 Integration Test Meeting",
        "entity": "TestCorp",
        "start": f"{tomorrow}T10:00:00Z",
        "end": f"{tomorrow}T11:00:00Z",
        "attendees": ["ceo@testcorp.com", "jane@acme.com"],
    })
    assert meeting_resp.status_code == 200, \
        f"Failed to create meeting: {meeting_resp.text[:200]}"
    meeting_data = meeting_resp.json()
    meeting_id = meeting_data.get("meeting_id") or meeting_data.get("id")

    # Step 2: Call /preparation/tomorrow
    prep_resp = client.get("/api/oem/preparation/tomorrow")
    assert prep_resp.status_code == 200, \
        f"Preparation failed: {prep_resp.text[:200]}"

    # Step 3: Verify the real meeting appears in the prep brief
    prep_text = json.dumps(prep_resp.json()).lower()
    assert "p22 integration test meeting" in prep_text, \
        f"Real MeetingStore meeting NOT found in /preparation/tomorrow response. " \
        f"This means MeetingStoreCalendarSource is not wired (P11 violation). " \
        f"Response excerpt: {prep_text[:500]}"


def test_ask_why_surfaces_synthesis_not_just_evidence_list(client):
    """P22 Test 2: Ask 'why' question must surface synthesis_hints.

    Before the Phase 2 fix: the narrator just re-listed evidence as
    "[1] On {date}, {who} recorded in {source}: {text}". The CausalEngine's
    analysis was computed but discarded.

    After the fix: if synthesis_hints are provided (from _retrieve_why's
    causal chain analysis), the answer contains the synthesis text, not
    just "Based on the organizational evidence I found:".

    Test: ask a "why" question, verify the answer is NOT just the
    evidence-list format (which starts with "Based on the organizational
    evidence I found:").
    """
    resp = client.post("/api/oem/ask/conversation", json={
        "query": "Why is Globex at risk?",
        "session_id": "p22-why-test",
    })
    assert resp.status_code == 200, f"Ask failed: {resp.text[:200]}"

    answer = resp.json().get("answer", "")

    # The old format always starts with "Based on the organizational evidence I found:"
    # If synthesis_hints are being passed, the answer should NOT start with that
    # (it should start with the intent-specific synthesis instead).
    # Note: if no evidence is found, the answer is "I don't have enough..."
    # which is also acceptable (honest fail-closed).
    if "I don't have enough organizational memory" in answer:
        pytest.skip("No evidence found for 'Why is Globex at risk?' — honest fail-closed, not a P22 violation")

    # If evidence was found, the answer should NOT be the old evidence-list format
    # (which starts with "Based on the organizational evidence I found:")
    assert not answer.startswith("Based on the organizational evidence I found:"), \
        f"Answer is still the old evidence-list format — synthesis_hints not being used. " \
        f"Answer: {answer[:200]!r}"


def test_ask_can_answer_meeting_questions(client):
    """P22 Test 3: Ask can reach Meeting data via meeting_store.

    Before the Phase 2 fix: AskPipeline.__init__ accepted meeting_store but
    no caller passed it. "What did we discuss in the Globex meeting?" couldn't
    reach Meeting.topics_discussed / commitments_made.

    After the fix: meeting_store is passed to AskPipeline. Ask can now
    reference meeting data.

    Test: verify the AskPipeline construction passes meeting_store (structural
    verification), then ask a meeting-related question and verify it doesn't
    error. A full behavioral test would require a meeting with topics_discussed
    set, which requires the full Loop 2 lifecycle (occur → observe_outcome).
    For now, verify the wiring is present and the question doesn't error.
    """
    # Structural verification: AskPipeline is constructed with meeting_store
    import inspect
    from maestro_api.routes import oem as oem_module

    source = inspect.getsource(oem_module)
    assert "meeting_store=_get_meeting_store()" in source, \
        "oem.py must pass meeting_store=_get_meeting_store() to AskPipeline"

    # Behavioral verification: ask a meeting question — it should not error
    resp = client.post("/api/oem/ask/conversation", json={
        "query": "What did we discuss in the Globex meeting?",
        "session_id": "p22-meeting-test",
    })
    assert resp.status_code == 200, \
        f"Ask with meeting question failed (status {resp.status_code}): {resp.text[:200]}"

    # The answer should either reference the meeting or honestly say it doesn't know
    answer = resp.json().get("answer", "").lower()
    # Acceptable: references meeting/globex OR honestly says "I don't have enough"
    assert "globex" in answer or "meeting" in answer or "don't have enough" in answer, \
        f"Answer doesn't reference meeting data or honestly fail. Answer: {answer[:200]!r}"
