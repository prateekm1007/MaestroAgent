"""Phase 10 comparison tests — Maestro vs frontier LLM vs human assistant."""

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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p10"
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


class TestPhase10Benchmark:
    """The 100-question comparison benchmark must exist."""

    def test_benchmark_has_100_questions(self):
        from comparison_benchmark_100 import get_comparison_benchmark
        qs = get_comparison_benchmark()
        assert len(qs) == 100

    def test_benchmark_has_6_categories(self):
        from comparison_benchmark_100 import get_benchmark_stats
        stats = get_benchmark_stats()
        assert len(stats) == 6
        expected = {"factual", "temporal", "commitment", "contradiction", "silence", "synthesis"}
        assert set(stats.keys()) == expected

    def test_questions_have_required_fields(self):
        from comparison_benchmark_100 import get_comparison_benchmark
        qs = get_comparison_benchmark()
        for q in qs:
            assert "question" in q
            assert "evidence_signals" in q
            assert "category" in q
            assert "reference_answer" in q
            assert "reference_entity" in q


class TestPhase10Comparison:
    """Maestro vs frontier LLM comparison."""

    def test_comparison_runs_without_crashing(self, isolated_api, client, auth_headers):
        from comparison_eval import evaluate_comparison
        report = evaluate_comparison(isolated_api, client, auth_headers,
                                     os.environ["MAESTRO_PERSONAL_DB"], "test-p10", limit=10)
        assert report["total_comparisons"] == 10
        assert "metrics" in report

    def test_comparison_reports_win_tie_loss(self, isolated_api, client, auth_headers):
        from comparison_eval import evaluate_comparison
        report = evaluate_comparison(isolated_api, client, auth_headers,
                                     os.environ["MAESTRO_PERSONAL_DB"], "test-p10", limit=10)
        assert "maestro_vs_llm_win_tie" in report["metrics"]
        assert "maestro_outright_win" in report["metrics"]
        assert "category_results" in report

    def test_comparison_scores_on_5_dimensions(self, isolated_api, client, auth_headers):
        """Each answer must be scored on 5 structural dimensions (per auditor)."""
        from comparison_eval import _score_answer
        q = {
            "reference_answer": "Alex committed to sending the proposal",
            "reference_entity": "Alex",
            "category": "factual",
        }
        score = _score_answer("Alex will send the proposal by Friday",
                              [{"text": "I will send the proposal", "entity": "Alex"}], q)
        # Structural dimensions (not keyword matching)
        assert "factual_accuracy" in score
        assert "evidence_traceability" in score
        assert "uncertainty_honesty" in score
        assert "intervention_restraint" in score
        assert "lifecycle_awareness" in score
        assert score["total"] <= 5

    def test_silence_questions_reward_restraint(self):
        """For silence questions, saying 'unknown' should score higher than guessing."""
        from comparison_eval import _score_answer
        q = {"reference_answer": "unknown", "reference_entity": "", "category": "silence"}
        restrained = _score_answer("I don't have enough information to answer.", [], q)
        guessing = _score_answer("The board will decide to invest in Q3.", [], q)
        # uncertainty_honesty replaces restraint
        assert restrained["uncertainty_honesty"] >= guessing["uncertainty_honesty"]

    def test_maestro_only_mode_when_no_llm(self, isolated_api, client, auth_headers):
        """When no real LLM is available, the eval should run in honest
        maestro-only mode — not simulate a fake LLM comparison."""
        from comparison_eval import evaluate_comparison
        report = evaluate_comparison(isolated_api, client, auth_headers,
                                     os.environ["MAESTRO_PERSONAL_DB"], "test-p10", limit=10)
        assert report["mode"] == "maestro_only"
        assert "disclaimer" in report
        # Win/tie should be 0 (no opponent)
        assert report["metrics"]["maestro_vs_llm_win_tie"]["value"] == 0.0


class TestPhase10HumanComparison:
    """Maestro vs human assistant comparison."""

    def test_human_comparison_runs(self):
        from comparison_eval import evaluate_human_assistant_comparison
        report = evaluate_human_assistant_comparison()
        assert report["total_comparisons"] == 20
        assert "maestro_vs_human_win_tie" in report["metrics"]

    def test_human_comparison_meets_target(self):
        """Maestro vs human win/tie >= 50%."""
        from comparison_eval import evaluate_human_assistant_comparison
        report = evaluate_human_assistant_comparison()
        rate = report["metrics"]["maestro_vs_human_win_tie"]
        assert rate["met"], \
            f"Maestro vs human win/tie {rate['value']} below target {rate['target']} ({rate['support']})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
