"""Phase 8 Copilot eval tests — benchmark structure + metrics + lift."""

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


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p8"
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


class TestPhase8Benchmark:
    """The 30-conversation Copilot benchmark must exist and cover all 14 features."""

    def test_benchmark_has_30_conversations(self):
        from copilot_benchmark_30 import get_copilot_benchmark
        convs = get_copilot_benchmark()
        assert len(convs) == 30

    def test_benchmark_covers_all_14_features(self):
        from copilot_benchmark_30 import get_all_features
        features = get_all_features()
        expected = {
            "interruptions", "filler", "corrections", "sarcasm",
            "tentative_statements", "changed_positions", "incomplete_sentences",
            "multiple_speakers", "ambiguous_pronouns", "explicit_commitments",
            "revoked_commitments", "negotiation_anchors", "concessions",
            "disagreement",
        }
        assert features == expected, f"Missing features: {expected - features}"

    def test_conversations_have_required_fields(self):
        from copilot_benchmark_30 import get_copilot_benchmark
        convs = get_copilot_benchmark()
        for c in convs:
            assert "conversation_id" in c
            assert "entity" in c
            assert "features" in c
            assert "transcript" in c
            assert "history_signals" in c
            assert "expected_commitments" in c
            assert "expected_revocations" in c
            assert "expected_suggestions" in c
            assert "forbidden_suggestions" in c

    def test_conversations_have_transcripts(self):
        from copilot_benchmark_30 import get_copilot_benchmark
        convs = get_copilot_benchmark()
        for c in convs:
            assert len(c["transcript"]) >= 1, f"Conversation {c['conversation_id']} has empty transcript"


class TestPhase8CopilotEval:
    """The copilot eval harness must run and produce metrics."""

    def test_eval_runs_without_crashing(self, isolated_api, client, auth_headers):
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=5)
        assert report["total_conversations"] == 5
        assert "metrics" in report

    def test_hallucination_rate_meets_target(self, isolated_api, client, auth_headers):
        """Hallucination rate must be <= 3% — this is LLM-independent."""
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=10)
        rate = report["metrics"]["hallucination_rate"]
        assert rate["met"], \
            f"Hallucination rate {rate['value']} exceeds target {rate['target']} ({rate['support']})"

    def test_p95_latency_meets_target(self, isolated_api, client, auth_headers):
        """P95 latency must be <= 3s — rule mode is fast."""
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=10)
        latency = report["metrics"]["p95_latency_ms"]
        assert latency["met"], \
            f"P95 latency {latency['value']}ms exceeds target {latency['target']}ms"

    def test_commitment_extraction_meets_target(self, isolated_api, client, auth_headers):
        """Commitment extraction accuracy must be >= 85%."""
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=10)
        acc = report["metrics"]["commitment_extraction_accuracy"]
        assert acc["met"], \
            f"Commitment extraction {acc['value']} below target {acc['target']} ({acc['support']})"

    def test_revocation_handling_meets_target(self, isolated_api, client, auth_headers):
        """Revocation handling accuracy must be >= 80%."""
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=10)
        acc = report["metrics"]["revocation_handling_accuracy"]
        assert acc["met"], \
            f"Revocation handling {acc['value']} below target {acc['target']} ({acc['support']})"

    def test_historical_context_lift_measured(self, isolated_api, client, auth_headers):
        """The lift between no-history and with-history must be measured."""
        from copilot_eval import evaluate_historical_context_lift
        report = evaluate_historical_context_lift(isolated_api, client, auth_headers,
                                                   os.environ["MAESTRO_PERSONAL_DB"], "test-p8")
        assert "no_history_score" in report
        assert "with_history_score" in report
        assert "lift" in report
        assert isinstance(report["lift"], (int, float))


class TestPhase8PostCallSummary:
    """Post-call summary must update the canonical world model."""

    def test_post_call_endpoint_exists(self, client, auth_headers):
        """The post-call summary endpoint must exist and accept requests."""
        # Seed a signal to get a situation
        client.post("/api/signals", json={
            "entity": "TestCorp", "text": "I will send the proposal",
            "signal_type": "commitment_made",
        }, headers=auth_headers)

        resp = client.post("/api/copilot/post-call", json={
            "situation_id": "test-situation",
            "transcript_chunks": [{"speaker": "TestCorp", "text": "I will send the proposal"}],
            "commitments": [{"entity": "TestCorp", "text": "send the proposal", "type": "explicit"}],
            "entity": "TestCorp",
        }, headers=auth_headers)
        # Should return 200 (or 200 with an error dict if Core bridge unavailable)
        assert resp.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
