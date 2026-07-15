"""
P1-1 regression test — Finding 7: "Memory answers not decision-grade."

Three code-fixable items (no LLM needed):

1. TEMPORAL LOWER BOUND: temporal_query.py produces both from_date and
   to_date, but api.py only passed to_date as as_of. Signals from before
   the quarter start leaked into "last quarter" answers. Fix: pass
   from_date to build_shell_async and get_relevant_signals.

2. ENTITY DISAMBIGUATION: Alex vs Alexa must NOT collapse. The
   _fuzzy_match substring check was too aggressive — "alex" is a substring
   of "alexa", so two different people were merged into one entity. Fix:
   only treat substring matches as matches when the remainder is a known
   corporate suffix (corp, inc, ltd) or empty.

3. ANSWER ABSTENTION: return "I don't have enough information" when no
   matching signals are found, instead of a generic template that gives
   the false impression of a searched-and-found answer.

Governance: P1 (execute), P2 (tests fail on old code), P22 (integration
test through REAL production entry points).
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p1-1"
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


def _login(client, user_email="p1-1@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": user_email,
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


# ===========================================================================
# Fix 1: Temporal lower bound — from_date filters out old signals
# ===========================================================================


class TestTemporalLowerBound:
    """"What did I commit to last quarter?" must NOT return signals from
    before the quarter start. The from_date (lower bound) must be enforced."""

    def test_from_date_filters_old_signals_in_build_shell(self, client):
        """build_shell with from_date must exclude signals before from_date."""
        from datetime import datetime, timezone, timedelta
        from maestro_personal_shell.api import build_shell

        headers = _login(client)

        # Create signals at different times
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=120)).isoformat()  # ~4 months ago
        recent_date = (now - timedelta(days=10)).isoformat()  # 10 days ago

        with _mock_llm()[0], _mock_llm()[1]:
            client.post("/api/signals", json={
                "entity": "OldCommitment",
                "text": "I will send the old proposal",
                "signal_type": "commitment_made",
                "timestamp": old_date,
            }, headers=headers)
            client.post("/api/signals", json={
                "entity": "RecentCommitment",
                "text": "I will send the new proposal",
                "signal_type": "commitment_made",
                "timestamp": recent_date,
            }, headers=headers)

        # Build shell with from_date = 30 days ago (should exclude old signal)
        from_date = (now - timedelta(days=30)).isoformat()
        shell = build_shell(user_email="p1-1@test.com", from_date=from_date)

        entities = [str(getattr(s, "entity", "")) for s in shell.oem_state.signals]
        assert "RecentCommitment" in entities, "Recent signal should be present"
        assert "OldCommitment" not in entities, (
            "P1-1 FAIL: Old signal (120 days ago) should be filtered out by "
            f"from_date={from_date}, but it's still in the shell. "
            f"Entities: {entities}"
        )

    def test_from_date_filters_in_get_relevant_signals(self, client):
        """get_relevant_signals with from_date must exclude old signals."""
        from datetime import datetime, timezone, timedelta
        from maestro_personal_shell.semantic_retrieval import get_relevant_signals, rebuild_fts_index

        headers = _login(client)
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=120)).isoformat()
        recent_date = (now - timedelta(days=5)).isoformat()

        with _mock_llm()[0], _mock_llm()[1]:
            client.post("/api/signals", json={
                "entity": "TempEntity",
                "text": "I will send the old proposal to TempEntity",
                "signal_type": "commitment_made",
                "timestamp": old_date,
            }, headers=headers)
            client.post("/api/signals", json={
                "entity": "TempEntity",
                "text": "I will send the new proposal to TempEntity",
                "signal_type": "commitment_made",
                "timestamp": recent_date,
            }, headers=headers)

        rebuild_fts_index()

        # Without from_date — should return both
        results_all = get_relevant_signals("TempEntity proposal", user_email="p1-1@test.com", limit=10)
        assert len(results_all) >= 2, f"Should find both signals, got {len(results_all)}"

        # With from_date = 30 days ago — should exclude the old one
        from_date = (now - timedelta(days=30)).isoformat()
        results_filtered = get_relevant_signals(
            "TempEntity proposal", user_email="p1-1@test.com", limit=10, from_date=from_date
        )
        texts = [r.get("text", "") for r in results_filtered]
        assert any("new proposal" in t for t in texts), "Recent signal should be present"
        assert not any("old proposal" in t for t in texts), (
            f"P1-1 FAIL: Old signal should be filtered out by from_date, "
            f"but 'old proposal' is still in results: {texts}"
        )


# ===========================================================================
# Fix 2: Entity disambiguation — Alex vs Alexa must NOT collapse
# ===========================================================================


class TestEntityDisambiguation:
    """Alex and Alexa are different people. The fuzzy matcher must NOT
    collapse them into one entity."""

    def test_alex_and_alexa_not_collapsed(self):
        """_fuzzy_match('Alex', 'Alexa') must return False."""
        from maestro_personal_shell.entity_resolver import _fuzzy_match
        assert not _fuzzy_match("Alex", "Alexa"), (
            "P1-1 FAIL: 'Alex' and 'Alexa' should NOT match — they are "
            "different names that share a prefix. The old substring check "
            "incorrectly matched them because 'alex' is in 'alexa'."
        )
        assert not _fuzzy_match("Alexa", "Alex"), (
            "P1-1 FAIL: reverse direction should also not match."
        )

    def test_alex_and_alexander_not_collapsed(self):
        """Alex and Alexander are different enough that a 1-char-prefix
        match should not collapse them (similarity = 4/9 = 0.44 < 0.85)."""
        from maestro_personal_shell.entity_resolver import _fuzzy_match
        assert not _fuzzy_match("Alex", "Alexander"), (
            "P1-1 FAIL: 'Alex' and 'Alexander' should NOT match via "
            "substring (remainder='ander', not a corporate suffix)."
        )

    def test_acme_and_acmecorp_still_match(self):
        """Corporate name variants must still match: Acme → AcmeCorp."""
        from maestro_personal_shell.entity_resolver import _fuzzy_match
        assert _fuzzy_match("Acme", "AcmeCorp"), (
            "P1-1 REGRESSION: 'Acme' and 'AcmeCorp' should still match "
            "(remainder='corp' is a corporate suffix). The fix broke this."
        )

    def test_acme_and_acme_corp_still_match(self):
        """Acme → Acme Corp (with space) must still match via normalization."""
        from maestro_personal_shell.entity_resolver import _fuzzy_match, _normalize
        # _normalize strips " corp" suffix → both become "acme"
        assert _normalize("Acme Corp") == _normalize("Acme"), (
            "Normalization should strip ' corp' suffix"
        )

    def test_resolve_entity_keeps_alex_and_alexa_separate(self):
        """resolve_entity must not resolve Alex to Alexa (or vice versa)
        when both are known entities."""
        from maestro_personal_shell.entity_resolver import resolve_entity
        known = ["Alex", "Alexa"]
        # Resolving "Alex" with Alexa in the known list must return "Alex"
        result = resolve_entity("Alex", known_entities=known)
        assert result == "Alex", (
            f"P1-1 FAIL: resolve_entity('Alex') returned '{result}' — "
            f"should return 'Alex', not collapse into 'Alexa'."
        )
        result = resolve_entity("Alexa", known_entities=known)
        assert result == "Alexa", (
            f"P1-1 FAIL: resolve_entity('Alexa') returned '{result}' — "
            f"should return 'Alexa', not collapse into 'Alex'."
        )


# ===========================================================================
# Fix 3: Answer abstention — "I don't have enough information"
# ===========================================================================


class TestAnswerAbstention:
    """When no evidence is found, Ask must return an honest abstention
    message, not a generic template."""

    def test_ask_returns_abstention_when_no_evidence(self, client):
        """Ask about a nonexistent entity must return 'I don't have enough
        information' — not a fabricated answer."""
        headers = _login(client)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            resp = client.post("/api/ask", json={
                "query": "What did NonexistentEntityXYZ commit to?",
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            answer = data.get("answer", "")
            assert "don't have enough information" in answer.lower() or \
                   "no matching signals" in answer.lower(), (
                f"P1-1 FAIL: Ask about a nonexistent entity should return "
                f"an abstention message, not a fabricated answer. "
                f"Got: '{answer[:200]}'"
            )
            assert data.get("confidence", 0) == 0, (
                f"Confidence should be 0 when no evidence exists. "
                f"Got: {data.get('confidence')}"
            )

    def test_ask_returns_real_answer_when_evidence_exists(self, client):
        """When evidence DOES exist, Ask must NOT return the abstention
        message — it must return a real answer."""
        headers = _login(client)

        with _mock_llm()[0], _mock_llm()[1], _mock_llm()[2]:
            client.post("/api/signals", json={
                "entity": "RealEntity",
                "text": "I will send the proposal to RealEntity by Friday",
                "signal_type": "commitment_made",
            }, headers=headers)

            resp = client.post("/api/ask", json={
                "query": "What did RealEntity commit to?",
            }, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            answer = data.get("answer", "")
            assert "don't have enough information" not in answer.lower(), (
                f"P1-1 FAIL: Ask about a real entity should NOT return "
                f"the abstention message. Got: '{answer[:200]}'"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
