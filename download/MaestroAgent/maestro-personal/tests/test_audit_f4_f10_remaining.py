"""
Verify Findings 4-10 from the independent audit.

F4: Completed commitments stay open — fix _detect_completion signal_type skip
F5: Graph fake 0.5 confidence — return None when no resolved edges
F6: silence_accuracy invalid — None when no data, honest labeling
F7: Dynamic agents mis-route engineering — add SLA/latency/incident lexicon
F8: Mutation kill rate hardcoded — already fixed, mutation 4 rewritten
F9: Live whispers silent for stale — override to "whisper" for stale_commitment
F10: Copilot REST requires situation_id — auto-bind from entity
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-audit-f4-f10"
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
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


def _login(client, email="audit@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _mock_llm():
    return (
        patch("maestro_personal_shell.commitment_classifier.classify_commitment",
              new_callable=AsyncMock,
              return_value={"commitment_type": "explicit", "is_commitment": True,
                            "confidence": 0.85, "state": "active", "owner": "user",
                            "reasoning": "test", "llm_powered": False}),
        patch("maestro_personal_shell.llm_bridge.llm_complete",
              new_callable=AsyncMock, return_value=None),
        patch("maestro_personal_shell.llm_bridge.is_llm_available",
              return_value=False),
    )


# F4: Completed commitments stay open
class TestCompletedCommitmentsFiltered:
    def test_completion_signal_closes_commitment(self, client):
        """A signal like 'Taylor confirmed receipt of redlines — closed'
        must close the original commitment, even when ingested as
        signal_type='commitment_made'."""
        from maestro_personal_shell.api import _detect_completion
        from maestro_personal_shell.personal_oem_state import PersonalSignal

        signals = [
            PersonalSignal(entity="Taylor", text="I will send Taylor the contract redlines",
                          signal_type="commitment_made", signal_id="sig-1"),
            # Completion signal — even though signal_type is commitment_made,
            # the text contains "closed" (past-tense completion keyword)
            PersonalSignal(entity="Taylor", text="Taylor confirmed receipt of redlines — closed",
                          signal_type="commitment_made", signal_id="sig-2"),
        ]
        completed = _detect_completion(signals)
        assert "sig-2" in completed, (
            f"P1-Audit-F4 FAIL: 'closed' should trigger completion detection "
            f"even for commitment_made signals. Got: {completed}"
        )

    def test_future_tense_not_treated_as_completion(self, client):
        """'I will send' must NOT be treated as a completion."""
        from maestro_personal_shell.api import _detect_completion
        from maestro_personal_shell.personal_oem_state import PersonalSignal

        signals = [
            PersonalSignal(entity="Test", text="I will send the proposal",
                          signal_type="commitment_made", signal_id="sig-1"),
            PersonalSignal(entity="Test", text="I will deliver the report",
                          signal_type="commitment_made", signal_id="sig-2"),
        ]
        completed = _detect_completion(signals)
        assert len(completed) == 0, (
            f"Future-tense signals should NOT be completions. Got: {completed}"
        )


# F5: Graph fake 0.5 confidence
class TestGraphHonestConfidence:
    def test_completion_rate_none_with_no_resolutions(self):
        """get_completion_rate must return None (not 0.5) when there are
        0 resolved edges."""
        from maestro_personal_shell.personal_graph import PersonalGraph
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            graph = PersonalGraph(db_path=db_path)
            rate = graph.get_completion_rate("NewEntity")
            assert rate is None, (
                f"P1-Audit-F5 FAIL: get_completion_rate should return None "
                f"with 0 resolutions, got {rate} (was 0.5 — fake confidence)"
            )
        finally:
            os.unlink(db_path)

    def test_predict_risk_unknown_with_no_data(self):
        """predict_risk must return risk_level='unknown' (not 'low'/'medium')
        when there's insufficient history."""
        from maestro_personal_shell.personal_graph import PersonalGraph
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            graph = PersonalGraph(db_path=db_path)
            graph.add_entity("TestEntity", entity_type="company")
            risk = graph.predict_risk("TestEntity")
            assert risk["risk_level"] == "unknown", (
                f"P1-Audit-F5 FAIL: risk_level should be 'unknown' with no "
                f"resolved commitments, got '{risk['risk_level']}'"
            )
            assert risk["completion_rate"] is None, (
                f"completion_rate should be None, got {risk['completion_rate']}"
            )
        finally:
            os.unlink(db_path)


# F6: silence_accuracy invalid
class TestSilenceAccuracyHonest:
    def test_silence_accuracy_none_with_no_data(self):
        """_compute_silence_accuracy must return None (not 0.5) when
        there are no behavior patterns."""
        from maestro_personal_shell.success_metrics import _compute_silence_accuracy
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            result = _compute_silence_accuracy(db_path, "no-data@test.com")
            assert result["silence_accuracy"] is None, (
                f"P1-Audit-F6 FAIL: silence_accuracy should be None with no "
                f"data, got {result['silence_accuracy']} (was 0.5 — fake)"
            )
            assert "silence_quality" in result, (
                "silence_quality field should exist (reserved for benchmark)"
            )
        finally:
            os.unlink(db_path)


# F7: Dynamic agents mis-route engineering
class TestEngineeringRouting:
    def test_sla_breach_routes_to_engineering(self):
        """'SLA breach latency incident' must route to engineering, not sales."""
        from maestro_personal_shell.dynamic_agents import select_relevant_agents
        agents = select_relevant_agents("SLA breach latency incident")
        assert "engineering" in agents, (
            f"P1-Audit-F7 FAIL: 'SLA breach latency incident' should route "
            f"to engineering, got {agents}"
        )

    def test_outage_routes_to_engineering(self):
        """'Production outage — pager duty' must route to engineering."""
        from maestro_personal_shell.dynamic_agents import select_relevant_agents
        agents = select_relevant_agents("Production outage — pager duty alert")
        assert "engineering" in agents, (
            f"Production outage should route to engineering, got {agents}"
        )

    def test_sales_still_works(self):
        """Sales queries must still route to sales (no regression)."""
        from maestro_personal_shell.dynamic_agents import select_relevant_agents
        agents = select_relevant_agents("Contract renewal negotiation with client")
        assert "sales" in agents, (
            f"Sales query should route to sales, got {agents}"
        )


# F9: Stale commitment whispers not silenced
class TestStaleWhispersNotSilenced:
    def test_stale_commitment_whisper_not_silent(self, client):
        """Stale commitment whispers must have delivery_route != 'silent'."""
        headers = _login(client)

        from datetime import datetime, timezone, timedelta
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            client.post("/api/signals", json={
                "entity": "StaleCorp",
                "text": "I will send the proposal to StaleCorp",
                "signal_type": "commitment_made",
                "timestamp": old_date,
            }, headers=headers)

            resp = client.get("/api/whisper", headers=headers)
            assert resp.status_code == 200
            whispers = resp.json()
            stale_whispers = [w for w in whispers if w.get("type") == "stale_commitment"]
            for w in stale_whispers:
                assert w["delivery_route"] != "silent", (
                    f"P1-Audit-F9 FAIL: stale commitment whisper has "
                    f"delivery_route='silent'. Should be 'whisper'. "
                    f"Whisper: {w}"
                )


# F10: Copilot REST auto-binds situation_id
class TestCopilotAutoBindSituation:
    def test_transcript_without_situation_id_works(self, client):
        """POST /api/copilot/transcript without situation_id must NOT
        return 422 — it should auto-bind from entity or use 'unknown'."""
        headers = _login(client)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            client.post("/api/signals", json={
                "entity": "CopilotTest",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=headers)

            resp = client.post("/api/copilot/transcript", json={
                "text": "We discussed the proposal timeline",
                "speaker": "prospect",
                "entity": "CopilotTest",
            }, headers=headers)
            assert resp.status_code != 422, (
                f"P1-Audit-F10 FAIL: transcript without situation_id returned "
                f"422. Should auto-bind. Status: {resp.status_code}, body: {resp.text[:200]}"
            )
            assert resp.status_code == 200, (
                f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
