"""
Test: commitment_classifier is wired into production endpoints.

S4 finding: the classifier existed and was tested, but production
endpoints didn't call it. This test verifies the wiring is real —
classification runs on ingest, filtering runs on read.
"""

import sys
import os
import tempfile
import json
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-s4"
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
    response = client.post("/api/auth/login", json={"password": "any"})
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


class TestClassifierWiringOnIngest:
    """S4: commitment_classifier must be called when a signal is created."""

    def test_classification_stored_in_metadata_on_ingest(self, client, auth_headers):
        """POST /api/signals must store commitment_type in metadata."""
        # Mock the classifier to return a known type
        mock_result = {
            "commitment_type": "explicit",
            "is_commitment": True,
            "confidence": 0.9,
            "state": "active",
            "owner": "user",
            "deadline_text": "Friday",
            "reasoning": "direct promise",
            "llm_powered": True,
        }

        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/api/signals",
                json={
                    "entity": "AcmeCorp",
                    "text": "I will send the proposal by Friday",
                    "signal_type": "commitment_made",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200

        # Verify the classification was stored in metadata
        import sqlite3
        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT metadata FROM signals WHERE entity = ?", ("AcmeCorp",)).fetchone()
        conn.close()

        meta = json.loads(row["metadata"])
        assert meta.get("commitment_type") == "explicit"
        assert meta.get("is_commitment") is True
        assert meta.get("commitment_state") == "active"
        assert meta.get("commitment_confidence") == 0.9

    def test_classifier_is_actually_called(self, client, auth_headers):
        """The classify_commitment function must be called — not just the import exist."""
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={
                "commitment_type": "explicit",
                "is_commitment": True,
                "confidence": 0.85,
                "state": "active",
                "owner": "user",
                "reasoning": "test",
                "llm_powered": False,
            },
        ) as mock_classify:
            client.post(
                "/api/signals",
                json={
                    "entity": "TestEntity",
                    "text": "I will send it",
                    "signal_type": "commitment_made",
                },
                headers=auth_headers,
            )
            # The classifier MUST have been called
            assert mock_classify.call_count == 1, \
                "classify_commitment must be called on every signal ingest"

    def test_classification_failure_is_non_fatal(self, client, auth_headers):
        """If the classifier fails, the signal must still be stored."""
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ):
            response = client.post(
                "/api/signals",
                json={
                    "entity": "FailEntity",
                    "text": "I will send it",
                    "signal_type": "commitment_made",
                },
                headers=auth_headers,
            )
            assert response.status_code == 200, \
                "Signal creation must succeed even if classification fails"


class TestClassifierFilterOnRead:
    """S4: non-commitments must be filtered out of Commitments endpoint."""

    def test_tentative_filtered_from_commitments(self, client, auth_headers):
        """A signal classified as 'tentative' must NOT appear in /api/commitments."""
        # Create a tentative signal (mock classifier says tentative)
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={
                "commitment_type": "tentative",
                "is_commitment": False,
                "confidence": 0.4,
                "state": "candidate",
                "owner": "user",
                "reasoning": "hedged with maybe",
                "llm_powered": True,
            },
        ):
            client.post(
                "/api/signals",
                json={
                    "entity": "TentativeEntity",
                    "text": "Maybe I can send it next week, but don't count on it",
                    "signal_type": "commitment_made",
                },
                headers=auth_headers,
            )

        # Create an explicit commitment (should appear)
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={
                "commitment_type": "explicit",
                "is_commitment": True,
                "confidence": 0.9,
                "state": "active",
                "owner": "user",
                "reasoning": "direct promise",
                "llm_powered": True,
            },
        ):
            client.post(
                "/api/signals",
                json={
                    "entity": "ExplicitEntity",
                    "text": "I will send the proposal by Friday",
                    "signal_type": "commitment_made",
                },
                headers=auth_headers,
            )

        # Get commitments — tentative must be filtered, explicit must appear
        response = client.get("/api/commitments", headers=auth_headers)
        assert response.status_code == 200
        commitments = response.json()

        entities = [c.get("entity", "") for c in commitments]
        assert "TentativeEntity" not in entities, \
            "S4: tentative signal must be filtered from /api/commitments"
        # ExplicitEntity should appear (it's a real commitment)
        assert "ExplicitEntity" in entities, \
            "S4: explicit commitment must appear in /api/commitments"

    def test_proposal_filtered_from_commitments(self, client, auth_headers):
        """A signal classified as 'proposal' must NOT appear in /api/commitments."""
        with patch(
            "maestro_personal_shell.commitment_classifier.classify_commitment",
            new_callable=AsyncMock,
            return_value={
                "commitment_type": "proposal",
                "is_commitment": False,
                "confidence": 0.5,
                "state": "candidate",
                "owner": "unknown",
                "reasoning": "suggestion not promise",
                "llm_powered": True,
            },
        ):
            client.post(
                "/api/signals",
                json={
                    "entity": "ProposalEntity",
                    "text": "We should deliver by Friday",
                    "signal_type": "commitment_made",
                },
                headers=auth_headers,
            )

        response = client.get("/api/commitments", headers=auth_headers)
        commitments = response.json()
        entities = [c.get("entity", "") for c in commitments]
        assert "ProposalEntity" not in entities, \
            "S4: proposal must be filtered from /api/commitments"

    def test_unclassified_not_filtered(self, client, auth_headers):
        """Signals without classification (backward compat) must NOT be filtered."""
        # Create a signal WITHOUT mocking the classifier (it'll fall back to rules
        # or fail gracefully, storing 'unclassified')
        client.post(
            "/api/signals",
            json={
                "entity": "UnclassifiedEntity",
                "text": "I will send it",
                "signal_type": "commitment_made",
            },
            headers=auth_headers,
        )

        response = client.get("/api/commitments", headers=auth_headers)
        commitments = response.json()
        entities = [c.get("entity", "") for c in commitments]
        # Unclassified signals should still appear (backward compat)
        assert "UnclassifiedEntity" in entities, \
            "S4: unclassified signals must not be filtered (backward compat)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
