"""
Roadmap fixes: 2.1 copilot commitment detection, 3.1 What Changed, 3.6 concurrency.
"""

import sys
import os
import tempfile
import asyncio
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-roadmap"
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


# 2.1: Copilot commitment detection
class TestCopilotCommitmentDetection:
    """The auditor found commitments_detected was always empty for transcript
    chunks. Fix: rule-based future-tense verb detection."""

    def test_detects_will_commitment(self, client, auth_headers):
        """Transcript with 'I will send' must detect a commitment."""
        from maestro_personal_shell.copilot_live import process_transcript_chunk
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        result = process_transcript_chunk(
            shell=shell,
            situation_id="test",
            text="I will send the proposal by Friday",
            speaker="prospect",
            entity="TestCorp",
        )
        commitments = result.get("commitments_detected", [])
        assert len(commitments) >= 1, (
            f"Should detect 'send the proposal' commitment. Got: {commitments}"
        )
        assert "proposal" in commitments[0]["text"].lower()
        assert commitments[0]["deadline"] == "Friday"

    def test_detects_need_to_commitment(self, client, auth_headers):
        """Transcript with 'I need to' must detect a commitment."""
        from maestro_personal_shell.copilot_live import process_transcript_chunk
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        result = process_transcript_chunk(
            shell=shell,
            situation_id="test",
            text="I need to review the contract by tomorrow",
            speaker="prospect",
            entity="TestCorp",
        )
        commitments = result.get("commitments_detected", [])
        assert len(commitments) >= 1, (
            f"Should detect 'review the contract' commitment. Got: {commitments}"
        )

    def test_no_commitment_in_plain_text(self, client, auth_headers):
        """Transcript without commitment keywords should return empty."""
        from maestro_personal_shell.copilot_live import process_transcript_chunk
        from maestro_personal_shell.shell import PersonalShell
        from maestro_personal_shell.personal_oem_state import PersonalOemState

        shell = PersonalShell(oem_state=PersonalOemState(signals=[]))
        result = process_transcript_chunk(
            shell=shell,
            situation_id="test",
            text="The weather is nice today",
            speaker="prospect",
            entity="TestCorp",
        )
        commitments = result.get("commitments_detected", [])
        assert len(commitments) == 0, (
            f"Plain text should not detect commitments. Got: {commitments}"
        )


# 3.1: What Changed returns results
class TestWhatChangedReturnsResults:
    """The auditor found What Changed returned 0 changes despite material
    changes existing. Fix: default since_timestamp to now-24h, not now."""

    def test_what_changed_returns_signals(self, client, auth_headers):
        """After ingesting a commitment, GET /api/what-changed must return it."""
        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            client.post("/api/signals", json={
                "entity": "WhatChangedCorp",
                "text": "I will send the proposal",
                "signal_type": "commitment_made",
            }, headers=auth_headers)

            resp = client.get("/api/what-changed", headers=auth_headers)
            assert resp.status_code == 200
            deltas = resp.json()
            entities = [d.get("entity", "") for d in deltas]
            assert "WhatChangedCorp" in entities, (
                f"What Changed should return the ingested signal. "
                f"Got entities: {entities}"
            )

    def test_what_changed_filters_noise(self, client, auth_headers):
        """Newsletter signals should NOT appear in What Changed."""
        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
            client.post("/api/signals", json={
                "entity": "NewsletterCorp",
                "text": "Weekly newsletter digest",
                "signal_type": "newsletter",
            }, headers=auth_headers)

            resp = client.get("/api/what-changed", headers=auth_headers)
            for d in resp.json():
                if d.get("entity") == "NewsletterCorp":
                    assert not d.get("is_meaningful"), (
                        "Newsletter should not be marked as meaningful"
                    )


# 3.6: Concurrency test
class TestConcurrentSignals:
    """20 concurrent POST /api/signals must all succeed with no 503 errors."""

    def test_20_concurrent_signal_creates(self, client, auth_headers):
        """20 concurrent signal creates must all succeed."""
        import threading
        import time

        results = []
        errors = []

        def create_signal(i):
            try:
                with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                           new_callable=AsyncMock,
                           return_value={"commitment_type": "explicit", "is_commitment": True,
                                         "confidence": 0.85, "state": "active", "owner": "user",
                                         "reasoning": "test", "llm_powered": False}), \
                     patch("maestro_personal_shell.llm_bridge.is_llm_available", return_value=False):
                    resp = client.post("/api/signals", json={
                        "entity": f"ConcurrentCorp{i}",
                        "text": f"I will send deliverable {i}",
                        "signal_type": "commitment_made",
                    }, headers=auth_headers)
                    results.append(resp.status_code)
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(20):
            t = threading.Thread(target=create_signal, args=(i,))
            threads.append(t)

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.time() - start

        # All should succeed (200)
        assert len(errors) == 0, f"Errors: {errors[:5]}"
        assert len(results) == 20, f"Only got {len(results)} results"
        for status in results:
            assert status == 200, f"Got status {status} — expected 200"

        # Verify all 20 signals are in the DB
        resp = client.get("/api/signals", headers=auth_headers)
        signals = resp.json()
        concurrent_entities = [s for s in signals if "ConcurrentCorp" in s.get("entity", "")]
        assert len(concurrent_entities) >= 20, (
            f"Expected 20 concurrent signals, got {len(concurrent_entities)}"
        )

        print(f"\n20 concurrent signals: {len(results)} succeeded in {elapsed:.1f}s")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
