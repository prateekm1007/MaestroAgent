"""
CRITICAL-1 fix: entity extraction regex must support alphanumerics.

The auditor found that asking "What did I promise Person0?" returned Carol's
data because the regex \b[A-Z][a-zA-Z]+\b doesn't match "Person0" (the digit
breaks it). When extraction fails, the fallback returns the first situation.

Fix: changed to \b[A-Z][a-zA-Z0-9_]+\b at all 4 locations in api.py.

This test verifies: asking about a nonexistent entity (Person0) must NOT
return another entity's data — it must abstain.
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-crit1"
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


@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/auth/login", json={"password": os.environ["MAESTRO_PERSONAL_TOKEN"]})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


class TestEntityExtractionFix:
    """CRITICAL-1: asking about a nonexistent entity must NOT return
    another entity's data."""

    def test_person0_query_does_not_return_carol(self, client, auth_headers):
        """Seed Carol, ask about Person0 — must abstain, not return Carol."""
        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            # Seed Carol
            client.post("/api/signals", json={
                "entity": "Carol",
                "text": "Carol promised to send report by Monday",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            # Ask about Person0 (doesn't exist)
            resp = client.post("/api/ask", json={
                "query": "What did I promise Person0?",
            }, headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()

            # MUST NOT return Carol's data
            source_entity = data.get("source_entity", "")
            answer = data.get("answer", "")
            evidence = data.get("evidence_refs", [])

            assert source_entity != "Carol", (
                f"CRITICAL: Query about Person0 returned Carol's data! "
                f"source_entity={source_entity}"
            )
            assert "Carol" not in answer, (
                f"CRITICAL: Carol's name appears in the answer for a Person0 query. "
                f"Answer: {answer[:200]}"
            )
            for ref in evidence:
                assert ref.get("entity", "") != "Carol", (
                    f"CRITICAL: Carol's data in evidence_refs for Person0 query. "
                    f"Ref: {ref}"
                )

    def test_person0_with_digits_extracted_correctly(self):
        """The regex must extract Person0, Person1, Entity42, etc."""
        import re
        # Test the new regex
        pattern = r'\b[A-Z][a-zA-Z0-9_]+\b'
        common_words = {"What", "Did", "Will", "The", "How", "When", "Why", "Who", "Is", "Are", "Can", "Could", "I"}

        test_cases = [
            ("What did Person0 promise?", ["Person0"]),
            ("What did I promise Person1?", ["Person1"]),
            ("What about Entity42?", ["Entity42"]),
            ("What did Alex Chen commit to?", ["Alex", "Chen"]),
            ("What did AcmeCorp promise?", ["AcmeCorp"]),
        ]

        for query, expected in test_cases:
            words = re.findall(pattern, query)
            entities = [w for w in words if w not in common_words]
            for exp in expected:
                assert exp in entities, (
                    f"Expected '{exp}' in extracted entities from '{query}', got: {entities}"
                )

    def test_nonexistent_entity_abstains(self, client, auth_headers):
        """Asking about NonexistentEntityXYZ must abstain."""
        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            client.post("/api/signals", json={
                "entity": "RealEntity",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            resp = client.post("/api/ask", json={
                "query": "What did NonexistentEntityXYZ commit to?",
            }, headers=auth_headers)
            data = resp.json()
            answer = data.get("answer", "").lower()
            assert "don't have enough information" in answer or "no signals found" in answer, (
                f"Should abstain for nonexistent entity. Got: {answer[:200]}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
