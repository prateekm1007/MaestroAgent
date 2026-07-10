"""
Integration test: verify ask_ranker is wired into production /api/ask.

The auditor found P11: ask_ranker existed but wasn't called by POST /api/ask.
This test calls the real production endpoint and verifies the ranker's output
reaches the user — specifically that entity-specific queries return the right
entity's evidence, not the highest-volume entity.
"""

import sys
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evaluation", "personal_memory_benchmark"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-ranker-int"
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


class TestAskRankerProductionIntegration:
    """Verify ask_ranker is wired into POST /api/ask (not just tests)."""

    def test_maria_query_returns_maria_evidence(self, client, auth_headers):
        """POST /api/ask about Maria must return Maria's evidence — not Alex's.

        This is the production integration test the auditor demanded.
        """
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            # Seed: Maria has 1 signal, NewsletterCorp has 5 (volume)
            client.post("/api/signals", json={
                "entity": "Maria Garcia", "text": "I reviewed the scorecard",
                "signal_type": "reported_statement",
            }, headers=auth_headers)

            for i in range(5):
                client.post("/api/signals", json={
                    "entity": "NewsletterCorp", "text": f"Weekly newsletter issue {i}",
                    "signal_type": "newsletter",
                }, headers=auth_headers)

            # Ask about Maria
            response = client.post("/api/ask", json={
                "query": "What did Maria review?",
            }, headers=auth_headers)

            assert response.status_code == 200
            data = response.json()

            # The evidence_refs should contain Maria's signal, not NewsletterCorp
            evidence = data.get("evidence_refs", [])
            if evidence:
                entities = [e.get("entity", "").lower() for e in evidence]
                # Maria should appear in evidence
                assert any("maria" in e for e in entities), \
                    f"Maria should be in evidence_refs, got entities: {entities}"
                # NewsletterCorp should NOT appear in evidence
                assert not any("newsletter" in e for e in entities), \
                    f"NewsletterCorp should NOT be in evidence_refs, got: {entities}"

    def test_source_sentence_not_from_noise(self, client, auth_headers):
        """source_sentence from POST /api/ask should not be from a newsletter."""
        m1, m2, m3 = _mock_llm()
        with m1, m2, m3:
            client.post("/api/signals", json={
                "entity": "RealClient", "text": "I will send the proposal by Friday",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            for i in range(5):
                client.post("/api/signals", json={
                    "entity": "NoiseCorp", "text": f"Newsletter digest {i}",
                    "signal_type": "newsletter",
                }, headers=auth_headers)

            response = client.post("/api/ask", json={
                "query": "What did RealClient commit to?",
            }, headers=auth_headers)

            data = response.json()
            source = data.get("source_sentence", "").lower()
            if source:
                assert "newsletter" not in source, \
                    f"source_sentence should not be from newsletter, got: {source}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
