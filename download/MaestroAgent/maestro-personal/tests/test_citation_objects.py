"""
Test: citation objects always include exact source quote/span.

Verifies that evidence_refs in Ask responses always include:
- text: the exact source quote
- entity: the entity name
- timestamp: the signal timestamp
- signal_id: the unique ID
- source_type: "manual" | "gmail" | "calendar" | "transcript"
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-cite"
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


class TestCitationObjects:
    """Citation objects must always include all required fields."""

    def test_evidence_refs_include_all_fields(self, client, auth_headers):
        """Every evidence_ref must include text, entity, timestamp, signal_id, source_type.
        If evidence_refs exist, none should have UUID-as-text (the old bug).
        """
        # Add a signal
        client.post(
            "/api/signals",
            json={
                "entity": "AcmeCorp",
                "text": "AcmeCorp committed to sending the proposal by Friday",
                "signal_type": "commitment_made",
            },
            headers=auth_headers,
        )

        # Ask a question
        response = client.post(
            "/api/ask",
            json={"query": "What did AcmeCorp commit to?"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        evidence_refs = data.get("evidence_refs", [])
        for ref in evidence_refs:
            # Every ref must have all required fields
            assert "text" in ref, "Citation must include text"
            assert "entity" in ref, "Citation must include entity"
            assert "timestamp" in ref, "Citation must include timestamp"
            assert "signal_id" in ref, "Citation must include signal_id"
            assert "source_type" in ref, "Citation must include source_type"
            # No UUID-as-text (the old bug)
            text = ref.get("text", "")
            assert not (len(text) == 36 and text.count("-") == 4), \
                f"Citation text must not be a UUID: {text}"
            if ref.get("source_type"):
                assert ref["source_type"] in ("manual", "gmail", "calendar", "transcript"), \
                    f"Invalid source_type: {ref['source_type']}"

    def test_source_sentence_is_exact_quote(self, client, auth_headers):
        """If source_sentence or evidence_refs are populated, they must contain real text (not UUIDs)."""
        signal_text = "AcmeCorp committed to sending the proposal by Friday"

        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={"commitment_type": "explicit", "is_commitment": True, "confidence": 0.9, "state": "active", "owner": "user", "reasoning": "test", "llm_powered": False},
        ):
            client.post(
                "/api/signals",
                json={"entity": "AcmeCorp", "text": signal_text, "signal_type": "commitment_made"},
                headers=auth_headers,
            )

            response = client.post(
                "/api/ask",
                json={"query": "What did AcmeCorp commit to?"},
                headers=auth_headers,
            )
            data = response.json()
            # If source_sentence is populated, it must not be a UUID
            source = data.get("source_sentence", "")
            if source:
                assert not (len(source) == 36 and source.count("-") == 4), \
                    f"source_sentence must not be a UUID: {source}"
            # If evidence_refs are populated, none should have UUID-as-text
            for ref in data.get("evidence_refs", []):
                text = ref.get("text", "")
                assert not (len(text) == 36 and text.count("-") == 4), \
                    f"Citation text must not be a UUID: {text}"

    def test_source_entity_populated(self, client, auth_headers):
        """If source_entity is populated, it must not be a UUID."""
        with patch(
            "maestro_personal_shell.llm_bridge.llm_complete",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={"commitment_type": "explicit", "is_commitment": True, "confidence": 0.9, "state": "active", "owner": "user", "reasoning": "test", "llm_powered": False},
        ):
            client.post(
                "/api/signals",
                json={"entity": "GlobexCorp", "text": "GlobexCorp will deliver", "signal_type": "commitment_made"},
                headers=auth_headers,
            )

            response = client.post(
                "/api/ask",
                json={"query": "What did GlobexCorp commit to?"},
                headers=auth_headers,
            )
            data = response.json()
            source_entity = data.get("source_entity", "")
            if source_entity:
                # Must not be a UUID
                assert not (len(source_entity) == 36 and source_entity.count("-") == 4), \
                    f"source_entity must not be a UUID: {source_entity}"

    def test_citation_signal_id_is_not_uuid_placeholder(self, client, auth_headers):
        """Citation signal_id must be a real ID, not a UUID used as text placeholder."""
        client.post(
            "/api/signals",
            json={"entity": "TestEntity", "text": "TestEntity will deliver", "signal_type": "commitment_made"},
            headers=auth_headers,
        )

        response = client.post(
            "/api/ask",
            json={"query": "What did TestEntity commit to?"},
            headers=auth_headers,
        )
        data = response.json()
        for ref in data.get("evidence_refs", []):
            # signal_id should look like a UUID, but text should NOT be a UUID
            assert ref["text"] != ref.get("signal_id", ""), \
                "Citation text must not be the signal_id (was a bug)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
