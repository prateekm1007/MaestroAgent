"""
Verify Findings 2 and 3 from the independent audit.

Finding 2 (CRITICAL product): Ask template collapse — 11/14 answers
collapsed to Alex Chen/Orion template. Fix: ranker-driven answer when
the rule-based answer doesn't mention the top evidence's entity.

Finding 3 (HIGH): Auth token printed on boot — already fixed (says
"token not logged for security"). This test verifies no token leakage.
"""

import sys
import os
import tempfile
import re
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-audit-f2"
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


def _login(client, email="f2@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _mock_llm():
    return (
        patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={
                "commitment_type": "explicit", "is_commitment": True,
                "confidence": 0.85, "state": "active", "owner": "user",
                "reasoning": "test", "llm_powered": False,
            },
        ),
        patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock, return_value=None,
        ),
        patch(
            "maestro_personal_shell.llm_bridge.is_llm_available",
            return_value=False,
        ),
    )


class TestAskRankerDrivenAnswer:
    """Finding 2: Ask must use ranker evidence to drive the answer, not
    default to the first situation's template."""

    def test_ask_mentions_queried_entity_not_template(self, client):
        """Ask about EntityB must return an answer mentioning EntityB,
        not a template about EntityA (the first situation)."""
        headers = _login(client)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            # Create signals for two different entities
            for entity, text in [
                ("AlphaCorp", "I will send the proposal to AlphaCorp by Friday"),
                ("BetaCorp", "I will send the contract to BetaCorp next week"),
                ("GammaCorp", "I will review the spec with GammaCorp tomorrow"),
            ]:
                client.post("/api/signals", json={
                    "entity": entity,
                    "text": text,
                    "signal_type": "commitment_made",
                }, headers=headers)

            # Ask about BetaCorp — the answer must mention BetaCorp
            resp = client.post("/api/ask", json={
                "query": "What did BetaCorp commit to?",
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            answer = data.get("answer", "")
            assert "BetaCorp" in answer, (
                f"P1-Audit-F2 FAIL: Ask about BetaCorp should mention BetaCorp. "
                f"Got: '{answer[:200]}'"
            )

    def test_ask_different_entities_get_different_answers(self, client):
        """Asking about different entities must produce different answers
        (not the same template for all)."""
        headers = _login(client)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            for entity, text in [
                ("DeltaCorp", "I will deliver the report to DeltaCorp on Monday"),
                ("EpsilonCorp", "I will send the invoice to EpsilonCorp on Tuesday"),
            ]:
                client.post("/api/signals", json={
                    "entity": entity,
                    "text": text,
                    "signal_type": "commitment_made",
                }, headers=headers)

            resp1 = client.post("/api/ask", json={
                "query": "What did DeltaCorp commit to?",
            }, headers=headers)
            resp2 = client.post("/api/ask", json={
                "query": "What did EpsilonCorp commit to?",
            }, headers=headers)

            answer1 = resp1.json().get("answer", "")
            answer2 = resp2.json().get("answer", "")

            assert "DeltaCorp" in answer1, f"Answer 1 should mention DeltaCorp: {answer1[:200]}"
            assert "EpsilonCorp" in answer2, f"Answer 2 should mention EpsilonCorp: {answer2[:200]}"
            assert answer1 != answer2, (
                f"Different entities should produce different answers. "
                f"Both got: '{answer1[:200]}'"
            )

    def test_ask_abstains_when_no_evidence(self, client):
        """Ask about a nonexistent entity must abstain (not template)."""
        headers = _login(client)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            client.post("/api/signals", json={
                "entity": "RealEntity",
                "text": "I will send the proposal to RealEntity",
                "signal_type": "commitment_made",
            }, headers=headers)

            resp = client.post("/api/ask", json={
                "query": "What did NonexistentEntityXYZ commit to?",
            }, headers=headers)
            assert resp.status_code == 200
            answer = resp.json().get("answer", "")
            assert "don't have enough information" in answer.lower(), (
                f"Should abstain for nonexistent entity. Got: '{answer[:200]}'"
            )


class TestNoTokenLeakage:
    """Finding 3: Auth token must NOT be printed to stdout or logs."""

    def test_main_does_not_print_token(self):
        """The main() function must not print the auth token."""
        import inspect
        from maestro_personal_shell.api import main
        source = inspect.getsource(main)
        # Check no f-string or print includes AUTH_TOKEN or env_token
        assert "AUTH_TOKEN}" not in source, (
            "main() source contains AUTH_TOKEN in an f-string — potential leak"
        )
        # Check no print includes the token value
        token_patterns = re.findall(r'print\(.*token.*\)', source, re.IGNORECASE)
        for p in token_patterns:
            assert "not logged" in p.lower() or "configured" in p.lower(), (
                f"main() prints something with 'token' that might leak: {p}"
            )

    def test_lifespan_does_not_log_token(self):
        """The lifespan function must not log the auth token."""
        import inspect
        from maestro_personal_shell.api import lifespan
        source = inspect.getsource(lifespan)
        assert "AUTH_TOKEN}" not in source, (
            "lifespan source contains AUTH_TOKEN in an f-string — potential leak"
        )
