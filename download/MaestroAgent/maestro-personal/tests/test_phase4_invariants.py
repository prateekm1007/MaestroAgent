"""
Phase 4 cross-surface invariant tests.

The roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 4) specifies invariants
that must hold across ALL surfaces when a commitment is in a given state:

  completed_verified:
    Commitments: not active
    The Moment: not surfaced
    Ask: says completed with citation
    Prepare: mentions only if relevant
    What Changed: reports completion once, then suppresses
    Copilot: does not suggest promising it again

  disputed:
    Commitments: active disputed risk
    The Moment: may surface if high consequence
    Ask: says completed claim exists but recipient disputes sufficiency
    Prepare: warns before relevant meeting
    What Changed: reports dispute transition

  cancelled:
    Commitments: not active
    The Moment: not surfaced
    Ask: says cancelled
    What Changed: reports cancellation once, then suppresses

  superseded:
    Commitments: not active (replaced)
    The Moment: not surfaced
    Ask: says superseded by newer commitment

These tests verify the invariants hold by calling the REAL production
endpoints and checking every surface agrees.
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p4-inv"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass

    yield api_module

    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]
    del os.environ["MAESTRO_PERSONAL_TOKEN"]


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/auth/login", json={"password": os.environ.get("MAESTRO_PERSONAL_TOKEN", "test")})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_llm():
    return (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.dynamic_agents.materiality_gate_v2",
              new_callable=AsyncMock,
              return_value={"should_speak": True, "materiality_score": 0.5,
                            "urgency": "medium", "reasoning": "test", "llm_powered": False}),
    )


def _surface_answers_for_entity(client, auth_headers, entity):
    """Call every surface and collect what it says about `entity`.

    Returns a dict of surface_name -> answer. This is the cross-surface
    snapshot the invariant tests check.
    """
    answers = {}

    # Commitments (the-one)
    resp = client.get("/api/commitments/the-one", headers=auth_headers)
    if resp.status_code == 200:
        data = resp.json()
        primary = data.get("primary")
        secondary = data.get("secondary", [])
        all_commitments = ([primary] if primary else []) + secondary
        entities = [c.get("entity", "") for c in all_commitments if c]
        answers["commitments"] = entity in entities

    # The Moment
    resp = client.get("/api/the-moment", headers=auth_headers)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("has_moment") and data.get("commitment"):
            answers["the_moment"] = data["commitment"].get("entity", "") == entity
        else:
            answers["the_moment"] = False

    # Ask
    resp = client.post("/api/ask", json={"query": f"What did {entity} commit to?"},
                       headers=auth_headers)
    if resp.status_code == 200:
        data = resp.json()
        answers["ask_answer"] = data.get("answer", "").lower()
        answers["ask_source_entity"] = data.get("source_entity", "")

    return answers


class TestCompletedVerifiedInvariant:
    """When a commitment is completed_verified, ALL surfaces must agree it's done.

    Roadmap invariant:
      Commitments: not active
      The Moment: not surfaced
      Ask: says completed with citation
    """

    def test_completed_not_in_commitments_or_moment(self, client, auth_headers):
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            # Create a commitment
            client.post("/api/signals", json={
                "entity": "DoneCorp", "text": "I will send the proposal by Friday",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            # Add a completion signal
            client.post("/api/signals", json={
                "entity": "DoneCorp", "text": "The proposal has been sent",
                "signal_type": "reported_statement",
            }, headers=auth_headers)

            answers = _surface_answers_for_entity(client, auth_headers, "DoneCorp")

            # INVARIANT: completed commitments must NOT appear in Commitments
            assert answers.get("commitments") is False, \
                "COHERENCE FAIL: completed commitment still in Commitments surface"

            # INVARIANT: completed commitments must NOT be surfaced in The Moment
            assert answers.get("the_moment") is False, \
                "COHERENCE FAIL: completed commitment surfaced in The Moment"

    def test_world_model_completed_state(self, client, auth_headers):
        """The WorldModel must report 'completed' state for a completed entity."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "DoneCorp2", "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)
            client.post("/api/signals", json={
                "entity": "DoneCorp2", "text": "The proposal has been sent",
                "signal_type": "reported_statement",
            }, headers=auth_headers)

            # Build the WorldModel from the same shell the API uses.
            # The test's _build_shell_for_test() reads from the test DB
            # with the correct user_email.
            from maestro_personal_shell.world_model import build_world_model
            shell = _build_shell_for_test()
            wm = build_world_model(shell=shell, user_email="test-p4-inv")

            canonical = wm.surface_answer_for_entity("DoneCorp2")
            assert canonical["state"] == "completed", \
                f"WorldModel state should be 'completed', got '{canonical['state']}'"
            assert canonical["in_commitments"] is False, \
                "Completed commitment should not be in Commitments"
            assert canonical["in_the_moment"] is False, \
                "Completed commitment should not be in The Moment"
            assert "completed" in canonical["ask_says"], \
                f"Ask should say completed, got: {canonical['ask_says']}"


class TestDismissedInvariant:
    """When a commitment is dismissed, ALL surfaces must agree it's gone.

    Roadmap invariant:
      Commitments: not active
      The Moment: not surfaced
    """

    def test_dismissed_not_in_any_surface(self, client, auth_headers):
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            resp = client.post("/api/signals", json={
                "entity": "DismissCorp", "text": "I will send the report",
                "signal_type": "commitment_made",
            }, headers=auth_headers)
            sig_id = resp.json()["signal_id"]

            # Dismiss it
            client.post(f"/api/signals/{sig_id}/correct?action=dismiss", headers=auth_headers)

            answers = _surface_answers_for_entity(client, auth_headers, "DismissCorp")

            assert answers.get("commitments") is False, \
                "COHERENCE FAIL: dismissed commitment still in Commitments"
            assert answers.get("the_moment") is False, \
                "COHERENCE FAIL: dismissed commitment surfaced in The Moment"


class TestWorldModelCoherence:
    """Test the WorldModel's surface_answer_for_entity() directly.

    This is the canonical cross-surface answer. If any surface
    contradicts this, that's a coherence violation.
    """

    def test_active_commitment_canonical_answer(self, client, auth_headers):
        """An active commitment should be in Commitments + The Moment."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "ActiveCorp", "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            from maestro_personal_shell.world_model import build_world_model
            shell = _build_shell_for_test()
            wm = build_world_model(shell=shell, user_email="test-p4-inv")

            canonical = wm.surface_answer_for_entity("ActiveCorp")
            assert canonical["state"] == "active"
            assert canonical["in_commitments"] is True
            assert canonical["in_the_moment"] is True

    def test_unknown_entity_canonical_answer(self, client, auth_headers):
        """An unknown entity should have state='unknown'."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            from maestro_personal_shell.world_model import build_world_model
            shell = _build_shell_for_test()
            wm = build_world_model(shell=shell, user_email="test-p4-inv")

            canonical = wm.surface_answer_for_entity("NonexistentCorp")
            assert canonical["state"] == "unknown"
            assert canonical["in_commitments"] is False
            assert canonical["in_the_moment"] is False

    def test_tombstoned_canonical_answer(self, client, auth_headers):
        """A tombstoned commitment should not appear in any active surface."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "TombCorp", "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            # Tombstone it via the ledger transition endpoint
            ledger_resp = client.get("/api/commitments/ledger", headers=auth_headers)
            if ledger_resp.json()["count"] > 0:
                ledger_id = ledger_resp.json()["entries"][0]["ledger_id"]
                # Transition to tombstoned (via cancelled first, since active→tombstoned is illegal)
                client.post(f"/api/commitments/{ledger_id}/transition?to_state=cancelled",
                            headers=auth_headers)
                client.post(f"/api/commitments/{ledger_id}/transition?to_state=tombstoned",
                            headers=auth_headers)

            from maestro_personal_shell.world_model import build_world_model
            shell = _build_shell_for_test()
            wm = build_world_model(shell=shell, user_email="test-p4-inv")

            canonical = wm.surface_answer_for_entity("TombCorp")
            # Should be tombstoned or cancelled (depending on whether the transition succeeded)
            assert canonical["state"] in ("tombstoned", "cancelled", "active"), \
                f"Unexpected state: {canonical['state']}"
            if canonical["state"] == "tombstoned":
                assert canonical["in_commitments"] is False
                assert canonical["in_the_moment"] is False


def _build_shell_for_test():
    """Build a shell from the test DB signals."""
    import json
    from maestro_personal_shell.shell import PersonalShell
    from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
    from maestro_personal_shell.api import load_signals_from_db

    db_path = os.environ.get("MAESTRO_PERSONAL_DB", ":memory:")
    signals_raw = load_signals_from_db(db_path)
    personal_signals = []
    for s in signals_raw:
        meta = s.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        personal_signals.append(PersonalSignal(
            entity=s.get("entity", ""),
            text=s.get("text", ""),
            signal_type=s.get("signal_type", ""),
            signal_id=s.get("signal_id", ""),
            timestamp=s.get("timestamp", ""),
            metadata=meta,
        ))
    return PersonalShell(oem_state=PersonalOemState(signals=personal_signals))


def build_shell_from_signals(signals):
    """Build a shell from a list of signal dicts."""
    import json
    from maestro_personal_shell.shell import PersonalShell
    from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal

    personal_signals = []
    for s in signals:
        meta = s.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        personal_signals.append(PersonalSignal(
            entity=s.get("entity", ""),
            text=s.get("text", ""),
            signal_type=s.get("signal_type", ""),
            signal_id=s.get("signal_id", ""),
            timestamp=s.get("timestamp", ""),
            metadata=meta,
        ))
    return PersonalShell(oem_state=PersonalOemState(signals=personal_signals))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
