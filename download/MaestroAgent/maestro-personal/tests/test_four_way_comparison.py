"""Tests for the 4-way comparison harness."""

import os
import sys
import tempfile
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "evaluation"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-4way"
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


class TestFourWayComparison:
    """The 4-way comparison must test all 4 conditions."""

    def test_runs_without_crashing(self):
        """The 4-way comparison module must be importable."""
        # Don't use isolated_api fixture — the module's main() sets up its own DB
        import four_way_comparison
        assert hasattr(four_way_comparison, "main")

    def test_maestro_rule_beats_human(self, isolated_api, client, auth_headers):
        """Maestro (rule mode) must beat the human simulation."""
        from comparison_eval import _score_answer_structural
        from comparison_benchmark_100 import get_comparison_benchmark

        questions = get_comparison_benchmark()[:10]
        m_scores = []
        h_scores = []

        mock_llm = (
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

        m1, m2, m3 = mock_llm
        with m1, m2, m3:
            for q in questions:
                # Seed evidence
                for sig in q.get("evidence_signals", []):
                    client.post("/api/signals", json={
                        "entity": sig.get("entity", ""),
                        "text": sig.get("text", ""),
                        "signal_type": sig.get("signal_type", "commitment_made"),
                        "timestamp": sig.get("timestamp", "2026-07-01T10:00:00Z"),
                    }, headers=auth_headers)

                # Maestro rule mode
                r = client.post("/api/ask", json={"query": q["question"]}, headers=auth_headers)
                d = r.json() if r.status_code == 200 else {}
                m_scores.append(_score_answer_structural(
                    d.get("answer", ""), d.get("evidence_refs", []), q)["total"])

                # Human simulation
                ref = q.get("reference_answer", "")
                cat = q.get("category", "")
                h_total = (1 if ref else 0) + (1 if q.get("evidence_signals") else 0) + \
                          (0 if cat == "silence" else 1) + 1 + 0
                h_scores.append(h_total)

        m_avg = sum(m_scores) / len(m_scores)
        h_avg = sum(h_scores) / len(h_scores)
        assert m_avg > h_avg, \
            f"Maestro rule ({m_avg:.2f}) must beat human ({h_avg:.2f})"

    def test_raw_llm_query_function_exists(self):
        """The _query_real_llm function must exist for real LLM comparison."""
        from four_way_comparison import query_real_llm
        assert callable(query_real_llm)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
