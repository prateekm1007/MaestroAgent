"""
P0-1 regression test — Finding 8: "Learning doesn't alter future behavior."

THE BUG (independent product audit):
    correct_signal() recorded ALL corrections — including dismissals — as
    behavior_type="correct_commitment". But learning_loop_v2.py:272 only
    counts behavior_type=="dismiss_suggestion" toward the dismissal rate.
    So dismissals never incremented the counter, dismissal_rate stayed 0.0,
    and materiality_gate_v2 never suppressed. The entire 8-phase learning
    loop was dead.

THE FIX:
    When action=="dismiss", correct_signal now records BOTH:
      - behavior_type="correct_commitment"  (existing — for outcome tracking)
      - behavior_type="dismiss_suggestion"  (NEW — for dismissal-rate learning)

THE PROOF (this test):
    A two-user A/B test. Alice dismisses 5 signals; Bob dismisses 0.
    After the dismissals:
      1. get_behavior_patterns("alice") returns dismissal_rate > 0.0
         (would be 0.0 on the old code — the regression guard).
      2. materiality_gate_v2 returns should_speak=False for Alice
         (suppressed — she dismisses too much) but should_speak=True for
         Bob (not suppressed — no dismissal history).
    Different dismissal histories → different speak decisions. That is
    "learning alters future behavior," which the audit proved was broken.

Governance: P1 (execute, don't read), P2 (test fails on old code), P7
(scoped state needs an isolation test — two users here), P22 (integration
test through the REAL production entry point: POST /api/signals/{id}/correct).
"""

import sys
import os
import tempfile
import sqlite3
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
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-p0-1"
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


def _login(client, user_email):
    """Login as a specific user_email (dev mode allows this)."""
    resp = client.post("/api/auth/login", json={
        "user_email": user_email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    assert resp.status_code == 200, f"Login failed for {user_email}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _mock_classifier_explicit():
    """Mock the classifier to return an explicit commitment (so signals persist)."""
    return patch(
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
    )


def _mock_llm_none():
    """Mock the LLM to return None (force rule-based fallback paths)."""
    return patch(
        "maestro_personal_shell.llm_bridge.llm_complete",
        new_callable=AsyncMock,
        return_value=None,
    )


# ===========================================================================
# Part 1: Direct DB verification — dismiss_suggestion rows are written
# ===========================================================================


class TestDismissSuggestionRecorded:
    """Prove the fix at the DB level: dismissing via the API writes a
    dismiss_suggestion row to user_behaviors (not just correct_commitment)."""

    def test_dismiss_writes_dismiss_suggestion_behavior(self, client):
        """POST /api/signals/{id}/correct?action=dismiss must record
        behavior_type='dismiss_suggestion' in the user_behaviors table.

        On the OLD code, only 'correct_commitment' was recorded — so this
        test FAILS on the old code (regression guard, P2)."""
        alice_headers = _login(client, "alice-p01@test.com")

        with _mock_classifier_explicit(), _mock_llm_none():
            # Create a commitment signal
            resp = client.post(
                "/api/signals",
                json={
                    "entity": "DismissCorp",
                    "text": "I will send the proposal by Friday",
                    "signal_type": "commitment_made",
                },
                headers=alice_headers,
            )
            assert resp.status_code == 200, resp.text
            sig_id = resp.json()["signal_id"]

            # Dismiss it
            resp = client.post(
                f"/api/signals/{sig_id}/correct?action=dismiss",
                headers=alice_headers,
            )
            assert resp.status_code == 200, resp.text

        # Query the user_behaviors table directly
        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT behavior_type, details FROM user_behaviors WHERE user_email = ?",
            ("alice-p01@test.com",),
        ).fetchall()
        conn.close()

        behavior_types = [r[0] for r in rows]
        assert "dismiss_suggestion" in behavior_types, (
            f"BUG P0-1: dismiss action did not record 'dismiss_suggestion' behavior. "
            f"Found behavior_types: {behavior_types}. "
            f"The learning loop's dismissal_rate counter only counts 'dismiss_suggestion' "
            f"(learning_loop_v2.py:272) — without it, dismissal_rate stays 0.0 forever "
            f"and materiality_gate_v2 never suppresses."
        )
        assert "correct_commitment" in behavior_types, (
            "The existing correct_commitment record should still be written "
            "(it's used for outcome tracking)."
        )

    def test_complete_does_not_write_dismiss_suggestion(self, client):
        """POST /api/signals/{id}/correct?action=complete must NOT record
        dismiss_suggestion (only dismissals count toward the dismissal rate)."""
        alice_headers = _login(client, "alice-p01b@test.com")

        with _mock_classifier_explicit(), _mock_llm_none():
            resp = client.post(
                "/api/signals",
                json={
                    "entity": "CompleteCorp",
                    "text": "I will send the proposal by Friday",
                    "signal_type": "commitment_made",
                },
                headers=alice_headers,
            )
            sig_id = resp.json()["signal_id"]

            client.post(
                f"/api/signals/{sig_id}/correct?action=complete",
                headers=alice_headers,
            )

        db_path = os.environ["MAESTRO_PERSONAL_DB"]
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT behavior_type FROM user_behaviors WHERE user_email = ?",
            ("alice-p01b@test.com",),
        ).fetchall()
        conn.close()

        behavior_types = [r[0] for r in rows]
        assert "dismiss_suggestion" not in behavior_types, (
            "action=complete should NOT record dismiss_suggestion — only "
            "action=dismiss should. Found: " + str(behavior_types)
        )


# ===========================================================================
# Part 2: get_behavior_patterns returns dismissal_rate > 0 after 5 dismissals
# ===========================================================================


class TestDismissalRateNonZero:
    """After dismissing 5 signals, get_behavior_patterns must return
    dismissal_rate > 0.0. On the OLD code this was always 0.0."""

    def test_dismissal_rate_after_5_dismissals(self, client):
        alice_headers = _login(client, "alice-rate@test.com")

        with _mock_classifier_explicit(), _mock_llm_none():
            # Create + dismiss 5 signals
            for i in range(5):
                resp = client.post(
                    "/api/signals",
                    json={
                        "entity": f"RateCorp{i}",
                        "text": f"I will send deliverable {i} by Friday",
                        "signal_type": "commitment_made",
                    },
                    headers=alice_headers,
                )
                sig_id = resp.json()["signal_id"]
                client.post(
                    f"/api/signals/{sig_id}/correct?action=dismiss",
                    headers=alice_headers,
                )

        from maestro_personal_shell.learning_loop_v2 import get_behavior_patterns
        patterns = get_behavior_patterns(user_email="alice-rate@test.com")

        assert patterns["total_behaviors"] >= 5, (
            f"Expected >= 5 behaviors, got {patterns['total_behaviors']}"
        )
        assert patterns["total_dismissals"] >= 5, (
            f"Expected >= 5 dismissals, got {patterns['total_dismissals']}. "
            f"On the OLD code (pre-P0-1 fix), this was 0 because dismissals "
            f"were recorded as 'correct_commitment', not 'dismiss_suggestion'."
        )
        assert patterns["dismissal_rate"] > 0.0, (
            f"Expected dismissal_rate > 0.0, got {patterns['dismissal_rate']}. "
            f"This is the exact bug the independent audit found: the learning "
            f"loop's dismissal_rate is always 0.0, so materiality_gate_v2 "
            f"never suppresses."
        )


# ===========================================================================
# Part 3: A/B test — different dismissal histories → different speak decisions
# ===========================================================================


class TestTwoUserABSpeakDecision:
    """The auditor's required proof: 'Write a two-user A/B test proving
    different dismissal histories produce different speak decisions.'

    Alice: dismisses 6 signals → dismissal_rate >= 0.6 → materiality_gate_v2
           suppresses low-urgency items (should_speak=False).
    Bob:   dismisses 0 signals → dismissal_rate == 0.0 → materiality_gate_v2
           does NOT suppress (should_speak=True from the base gate).

    Same low-urgency commitment, different speak decision. That is
    'learning alters future behavior.'"""

    def test_alice_suppressed_bob_not_suppressed(self, client):
        alice_headers = _login(client, "alice-ab@test.com")
        bob_headers = _login(client, "bob-ab@test.com")

        with _mock_classifier_explicit(), _mock_llm_none():
            # Alice dismisses 6 signals (6 dismissals / 6 total = 1.0 rate)
            for i in range(6):
                resp = client.post(
                    "/api/signals",
                    json={
                        "entity": f"AliceCorp{i}",
                        "text": f"I will send deliverable {i}",
                        "signal_type": "commitment_made",
                    },
                    headers=alice_headers,
                )
                sig_id = resp.json()["signal_id"]
                client.post(
                    f"/api/signals/{sig_id}/correct?action=dismiss",
                    headers=alice_headers,
                )

            # Bob creates 1 signal but does NOT dismiss it
            client.post(
                "/api/signals",
                json={
                    "entity": "BobCorp",
                    "text": "I will review the spec",
                    "signal_type": "commitment_made",
                },
                headers=bob_headers,
            )

        # Verify the behavior patterns diverge
        from maestro_personal_shell.learning_loop_v2 import get_behavior_patterns
        alice_patterns = get_behavior_patterns(user_email="alice-ab@test.com")
        bob_patterns = get_behavior_patterns(user_email="bob-ab@test.com")

        assert alice_patterns["dismissal_rate"] > 0.6, (
            f"Alice should have dismissal_rate > 0.6 (she dismissed 6/6). "
            f"Got: {alice_patterns['dismissal_rate']}"
        )
        assert bob_patterns.get("dismissal_rate", 0.0) == 0.0, (
            f"Bob should have dismissal_rate == 0.0 (he dismissed nothing). "
            f"Got: {bob_patterns.get('dismissal_rate', 0.0)}"
        )

        # Now feed the SAME low-urgency commitment to materiality_gate_v2
        # for both users. The base gate returns urgency="low" for a simple
        # commitment with no stale/deadline context (materiality_gate.py:142).
        # Alice (dismissal_rate > 0.6) should be suppressed; Bob should not.
        from maestro_personal_shell.dynamic_agents import materiality_gate_v2

        commitment = {
            "entity": "TestCorp",
            "text": "I will send the proposal",
            "claim_type": "commitment",
        }
        # No days_stale, no has_deadline → base gate returns urgency="low"
        context = {}

        alice_result = asyncio.run(
            materiality_gate_v2(commitment, context, user_email="alice-ab@test.com")
        )
        bob_result = asyncio.run(
            materiality_gate_v2(commitment, context, user_email="bob-ab@test.com")
        )

        assert alice_result["should_speak"] is False, (
            f"Alice (dismissal_rate={alice_patterns['dismissal_rate']}) should be "
            f"SUPPRESSED by materiality_gate_v2 — she dismisses >60% of low-urgency "
            f"suggestions. Got should_speak={alice_result['should_speak']}, "
            f"reasoning={alice_result.get('reasoning', '')}. "
            f"On the OLD code, Alice would NOT be suppressed because her "
            f"dismissal_rate was always 0.0 (the P0-1 bug)."
        )
        assert alice_result.get("behavior_adjusted") is True, (
            "Alice's suppression must be behavior-adjusted (learning-driven), "
            "not just the base gate happening to return False."
        )

        assert bob_result["should_speak"] is True, (
            f"Bob (dismissal_rate=0.0) should NOT be suppressed — no dismissal "
            f"history to justify suppression. Got should_speak={bob_result['should_speak']}. "
            f"The SAME commitment produces a DIFFERENT speak decision for Bob vs Alice. "
            f"That is 'learning alters future behavior.'"
        )

        # The A/B divergence is the proof
        assert alice_result["should_speak"] != bob_result["should_speak"], (
            "A/B FAIL: Alice and Bob got the SAME speak decision for the same "
            "commitment. The learning loop is not altering behavior. "
            f"Alice={alice_result['should_speak']}, Bob={bob_result['should_speak']}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
