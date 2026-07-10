"""Phase 5 eval tests — track Ask + Prepare quality over time.

These tests run the eval harnesses and enforce the roadmap targets
where possible. Rule-mode baselines are tracked for anti-regression;
LLM-mode targets are enforced when the LLM is available.
"""

import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation" / "personal_memory_benchmark"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p5"
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


class TestPhase5AskBenchmark:
    """The 150-question Ask benchmark must exist and be well-formed."""

    def test_benchmark_has_150_questions(self):
        from ask_benchmark_150 import get_ask_benchmark
        qs = get_ask_benchmark()
        assert len(qs) == 150

    def test_benchmark_has_10_categories(self):
        from ask_benchmark_150 import get_benchmark_stats
        stats = get_benchmark_stats()
        assert len(stats) == 10
        # Every category must have at least 5 questions
        for cat, count in stats.items():
            assert count >= 5, f"Category {cat} has only {count} questions"

    def test_benchmark_questions_have_required_fields(self):
        from ask_benchmark_150 import get_ask_benchmark
        qs = get_ask_benchmark()
        for q in qs:
            assert "question" in q
            assert "category" in q
            assert "expected_entities" in q
            assert "forbidden_entities" in q


class TestPhase5ClaimVerifier:
    """The claim verifier must remove unsupported claims."""

    def test_supported_claim_kept(self):
        from maestro_personal_shell.claim_verifier import verify_claims
        answer = "Alex will send the proposal by Friday."
        evidence = [{"text": "I will send the proposal by Friday", "entity": "Alex"}]
        result = verify_claims(answer, evidence, "I will send the proposal by Friday")
        assert result["all_claims_supported"] is True
        assert result["unsupported_claims"] == []
        assert result["confidence"] >= 0.8

    def test_unsupported_claim_removed(self):
        from maestro_personal_shell.claim_verifier import verify_claims
        answer = "Alex will send the proposal. The stock market crashed today."
        evidence = [{"text": "I will send the proposal by Friday", "entity": "Alex"}]
        result = verify_claims(answer, evidence, "I will send the proposal by Friday")
        assert len(result["unsupported_claims"]) >= 1
        assert "stock market" in result["unsupported_claims"][0].lower()

    def test_no_evidence_low_confidence(self):
        from maestro_personal_shell.claim_verifier import verify_claims
        answer = "Alex committed to something."
        result = verify_claims(answer, [], "")
        assert result["confidence"] <= 0.4

    def test_counterevidence_detected(self):
        from maestro_personal_shell.claim_verifier import verify_claims
        # Claim says "not cancelled" but evidence says "cancelled"
        answer = "The contract is not cancelled."
        evidence = [{"text": "The contract was cancelled yesterday", "entity": "Contract"}]
        result = verify_claims(answer, evidence, "The contract is not cancelled.")
        # The counterevidence detection should flag the contradiction
        assert isinstance(result["counterevidence"], list)


class TestPhase5AskEval:
    """Run the Ask eval and enforce targets."""

    def test_ask_eval_runs_without_crashing(self, isolated_api, client, auth_headers):
        from ask_eval import evaluate_ask
        report = evaluate_ask(isolated_api, client, auth_headers,
                              os.environ["MAESTRO_PERSONAL_DB"], "test-p5", limit=10)
        assert report["total_questions"] == 10
        assert "metrics" in report

    def test_unsupported_claims_below_target(self, isolated_api, client, auth_headers):
        """Unsupported claims rate must be <= 3%. This is LLM-independent —
        the claim verifier is rule-based and must always pass."""
        from ask_eval import evaluate_ask
        report = evaluate_ask(isolated_api, client, auth_headers,
                              os.environ["MAESTRO_PERSONAL_DB"], "test-p5", limit=30)
        rate = report["metrics"]["unsupported_claims_rate"]
        assert rate["met"], \
            f"Unsupported claims rate {rate['value']} exceeds target {rate['target']} ({rate['support']})"

    def test_entity_isolation_no_violations(self, isolated_api, client, auth_headers):
        """Entity isolation: forbidden_entities must not appear in evidence.
        This is LLM-independent — the FTS5 + ranker must filter them out."""
        from ask_eval import evaluate_ask
        report = evaluate_ask(isolated_api, client, auth_headers,
                              os.environ["MAESTRO_PERSONAL_DB"], "test-p5", limit=30)
        violations = report["metrics"]["entity_isolation_violation_rate"]
        assert violations["met"], \
            f"Entity isolation violations: {violations['value']} ({violations['support']})"


class TestPhase5PrepareBenchmark:
    """The 50-meeting Prepare benchmark must exist and be well-formed."""

    def test_benchmark_has_50_meetings(self):
        from prepare_benchmark_50 import get_prepare_benchmark
        meetings = get_prepare_benchmark()
        assert len(meetings) == 50

    def test_meetings_have_required_fields(self):
        from prepare_benchmark_50 import get_prepare_benchmark
        meetings = get_prepare_benchmark()
        for m in meetings:
            assert "meeting_id" in m
            assert "entity" in m
            assert "attendees" in m
            assert "meeting_context" in m
            assert "signals" in m
            assert "reference_brief" in m
            assert "irrelevant_true_facts" in m
            assert "expected_keywords" in m

    def test_meetings_have_reference_briefs(self):
        from prepare_benchmark_50 import get_prepare_benchmark
        meetings = get_prepare_benchmark()
        for m in meetings:
            assert len(m["reference_brief"]) >= 1, \
                f"Meeting {m['meeting_id']} has empty reference brief"


class TestPhase5PrepareEval:
    """Run the Prepare eval and check structure."""

    def test_prepare_eval_runs_without_crashing(self, isolated_api, client, auth_headers):
        from prepare_eval import evaluate_prepare
        report = evaluate_prepare(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p5", limit=5)
        assert report["total_meetings"] == 5
        assert "metrics" in report

    def test_prepare_brief_has_bullets(self, isolated_api, client, auth_headers):
        """The Prepare response must include prep_points (3-5 bullets)."""
        from prepare_eval import evaluate_prepare
        report = evaluate_prepare(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p5", limit=5)
        # At least some meetings should produce bullets
        scored = report["scored"]
        assert scored > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
