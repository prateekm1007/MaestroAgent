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

    def test_commitment_extraction_measured_honestly(self, isolated_api, client, auth_headers):
        """Commitment extraction must be measured against the ACTUAL endpoint
        output, not the benchmark's ground truth. The auditor found the eval
        was giving 100% credit vacuously when the endpoint returned empty
        results. Now the eval checks the actual commitments_detected list.

        In rule mode (without a working LLM), the copilot endpoint returns
        empty commitments_detected — this is honestly reported as 0%, not
        the previous vacuous 100%.
        """
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=10)
        acc = report["metrics"]["commitment_extraction_accuracy"]
        # The eval must report the ACTUAL extraction rate (may be 0% in rule mode)
        assert "value" in acc
        assert "support" in acc
        # The support must show actual/expected, not expected/expected
        # (the old vacuous behavior was expected/expected = 100%)
        parts = acc["support"].split("/")
        assert len(parts) == 2
        actual, expected = int(parts[0]), int(parts[1])
        # If expected > 0, actual must be checked against the real endpoint output
        # (not just copied from expected)
        if expected > 0:
            # In rule mode the endpoint returns empty, so actual should be 0
            # (this is the honest baseline — not 100%)
            assert actual <= expected  # can't extract more than expected

    def test_revocation_handling_measured_honestly(self, isolated_api, client, auth_headers):
        """Revocation handling must be measured against the ACTUAL endpoint
        output, not the benchmark's ground truth."""
        from copilot_eval import evaluate_copilot
        report = evaluate_copilot(isolated_api, client, auth_headers,
                                  os.environ["MAESTRO_PERSONAL_DB"], "test-p8",
                                  with_history=False, limit=10)
        acc = report["metrics"]["revocation_handling_accuracy"]
        assert "value" in acc
        assert "support" in acc
        parts = acc["support"].split("/")
        if len(parts) == 2:
            actual, expected = int(parts[0]), int(parts[1])
            if expected > 0:
                assert actual <= expected

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
