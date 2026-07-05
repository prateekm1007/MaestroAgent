"""
V8 Upgrade #3 — Conversational Curiosity. Regression tests.

Acceptance criteria (from the V8 spec):
  1. POST /api/oem/curiosity/follow-up returns either a follow_up_question
     OR {"understanding_updated": true, "signal_created": true}
  2. Follow-up questions reference the previous answer (not generic)
  3. Max 3 turns per topic (Maestro does not interrogate)
  4. After the conversation, a new signal is created (verified: signal
     appears in model)
  5. TODAY shows a conversation flow (not a single Q&A)
  6. V5 litmus: no new panel. V8 litmus: the org teaches Maestro through
     conversation — builds trust.

These tests cover criteria 1, 2, 3, 4, and 6 at the backend level.
Criterion 5 (TODAY visual) is covered by static file checks.
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from maestro_oem import OEMEngine
from maestro_oem.curiosity import CuriosityEngine
from maestro_oem.signal import ExecutionSignal, SignalType


# Fixture — build the FastAPI app with demo seed.
@pytest.fixture(scope="module")
def client():
    """Build the FastAPI app with the OEM initialized (demo seed loaded)."""
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_v8_conv_curiosity_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _cleanup_conversation_state():
    """Clean up conversation state + any ingested human_context signals
    after each test, so the shared oem_state singleton isn't polluted.

    oem_state is a module-level singleton shared across all test files.
    Conversational curiosity tests ingest human_context signals via
    live_ingest. Without cleanup, those signals persist and affect other
    test files (e.g. test_v8_explanations expects the demo seed's signal
    count, not demo + conversation signals).
    """
    CuriosityEngine._conversations.clear()
    yield
    # After the test: clear conversation state and remove any
    # human_context signals that were ingested during the test.
    # We only remove the signals from the list — we do NOT call
    # _refresh_downstream() because that rebuilds the engine from
    # the (now-trimmed) signal list, which would lose the demo seed's
    # learning objects and laws. The human_context signals are
    # DECISION_SIGNALs that don't produce learning objects anyway
    # (the model's process_signal only creates LOs for PR/review/doc
    # signals), so removing them from the list is sufficient.
    CuriosityEngine._conversations.clear()
    try:
        from maestro_api.oem_state import oem_state
        before_count = len(oem_state.signals)
        oem_state.signals = [
            s for s in oem_state.signals
            if s.metadata.get("kind") != "human_context"
        ]
        removed = before_count - len(oem_state.signals)
        if removed > 0:
            oem_state._live_signals_ingested = max(0, oem_state._live_signals_ingested - removed)
    except Exception:
        pass


# ============================================================
# Acceptance Criterion 1 — returns follow_up_question OR understanding_updated
# ============================================================

class TestFollowUpReturnType:
    """follow_up() must return one of two shapes."""

    def test_turn_1_returns_follow_up_question(self) -> None:
        """Turn 1 must return a follow_up_question, not understanding_updated."""
        engine = OEMEngine()
        model = engine.get_model()
        c = CuriosityEngine(model, [])
        # Clear any leftover conversation state
        CuriosityEngine._conversations.clear()
        result = c.follow_up(
            question_id="cq-test-1",
            answer="We lack tooling",
            original_question="Why is payments unmeasured?",
            question_type="unmeasured_domain",
            domain="payments",
        )
        assert result["understanding_updated"] is False
        assert result["signal_created"] is False
        assert "follow_up_question" in result
        assert isinstance(result["follow_up_question"], str)
        assert len(result["follow_up_question"]) > 10
        CuriosityEngine._conversations.clear()

    def test_turn_3_returns_understanding_updated(self) -> None:
        """After 3 turns, must return understanding_updated=True + signal_created=True."""
        engine = OEMEngine()
        model = engine.get_model()
        c = CuriosityEngine(model, [])
        CuriosityEngine._conversations.clear()
        # Turn 1
        c.follow_up("cq-test-2", "Answer 1", original_question="Q1",
                    question_type="unmeasured_domain", domain="payments")
        # Turn 2
        c.follow_up("cq-test-2", "Answer 2")
        # Turn 3
        result = c.follow_up("cq-test-2", "Answer 3")
        assert result["understanding_updated"] is True
        assert result["signal_created"] is True
        assert "signal_id" in result
        assert "summary" in result
        assert result["turn"] == 3
        CuriosityEngine._conversations.clear()

    def test_missing_question_id_returns_error(self) -> None:
        """Missing question_id must return an error, not crash."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        result = c.follow_up("", "some answer")
        assert result["understanding_updated"] is False
        assert result["signal_created"] is False
        assert "error" in result

    def test_missing_answer_returns_error(self) -> None:
        """Missing answer must return an error."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        result = c.follow_up("cq-test-3", "")
        assert result["understanding_updated"] is False
        assert "error" in result

    def test_new_conversation_requires_original_question(self) -> None:
        """Starting a new conversation without original_question must error."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        CuriosityEngine._conversations.clear()
        result = c.follow_up("cq-new-1", "an answer")  # no original_question
        assert result["understanding_updated"] is False
        assert "error" in result
        CuriosityEngine._conversations.clear()


# ============================================================
# Acceptance Criterion 2 — follow-ups reference the previous answer
# ============================================================

class TestFollowUpReferencesAnswer:
    """Follow-up questions must reference the user's previous answer."""

    def test_follow_up_contains_answer_snippet(self) -> None:
        """The follow-up question must contain a snippet of the user's answer."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        CuriosityEngine._conversations.clear()
        user_answer = "We need Datadog dashboards to measure this"
        result = c.follow_up(
            "cq-ref-1", user_answer,
            original_question="Why is payments unmeasured?",
            question_type="unmeasured_domain",
            domain="payments",
        )
        follow_up = result["follow_up_question"]
        # The follow-up must reference the answer (at least a snippet)
        # We check that at least 2 consecutive words from the answer appear
        answer_words = user_answer.split()
        found = False
        for i in range(len(answer_words) - 1):
            snippet = " ".join(answer_words[i:i+2])
            if snippet.lower() in follow_up.lower():
                found = True
                break
        assert found, (
            f"Follow-up question does not reference the user's answer. "
            f"Answer: '{user_answer}' | Follow-up: '{follow_up}'"
        )
        CuriosityEngine._conversations.clear()

    def test_different_answers_produce_different_follow_ups(self) -> None:
        """Different answers must produce different follow-up questions (not hardcoded)."""
        engine = OEMEngine()
        CuriosityEngine._conversations.clear()

        # First conversation with answer A
        c1 = CuriosityEngine(engine.get_model(), [])
        r1 = c1.follow_up(
            "cq-diff-1", "We lack tooling",
            original_question="Q", question_type="unmeasured_domain", domain="payments",
        )

        # Second conversation with answer B
        c2 = CuriosityEngine(engine.get_model(), [])
        r2 = c2.follow_up(
            "cq-diff-2", "Nobody has time",
            original_question="Q", question_type="unmeasured_domain", domain="payments",
        )

        assert r1["follow_up_question"] != r2["follow_up_question"], (
            "Different answers produced identical follow-ups — content is hardcoded."
        )
        CuriosityEngine._conversations.clear()


# ============================================================
# Acceptance Criterion 3 — max 3 turns per topic
# ============================================================

class TestMaxThreeTurns:
    """Maestro must not interrogate — conversations are bounded at 3 turns."""

    def test_conversation_closes_after_3_turns(self) -> None:
        """After exactly 3 turns, the conversation must close with understanding_updated."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        CuriosityEngine._conversations.clear()

        # Turn 1 — should return follow_up (turn 2)
        r1 = c.follow_up("cq-max-1", "A1", original_question="Q",
                         question_type="unmeasured_domain", domain="payments")
        assert r1["understanding_updated"] is False
        assert r1["turn"] == 2

        # Turn 2 — should return follow_up (turn 3)
        r2 = c.follow_up("cq-max-1", "A2")
        assert r2["understanding_updated"] is False
        assert r2["turn"] == 3

        # Turn 3 — should close
        r3 = c.follow_up("cq-max-1", "A3")
        assert r3["understanding_updated"] is True
        assert r3["turn"] == 3  # still turn 3, not 4
        CuriosityEngine._conversations.clear()

    def test_conversation_does_not_exceed_3_turns(self) -> None:
        """The conversation must not go past turn 3."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        CuriosityEngine._conversations.clear()

        c.follow_up("cq-max-2", "A1", original_question="Q",
                    question_type="unmeasured_domain", domain="payments")
        c.follow_up("cq-max-2", "A2")
        r3 = c.follow_up("cq-max-2", "A3")
        assert r3["understanding_updated"] is True

        # The conversation state should be cleaned up — a 4th call should
        # start a NEW conversation (requiring original_question again)
        r4 = c.follow_up("cq-max-2", "A4")  # no original_question
        assert r4["understanding_updated"] is False
        assert "error" in r4  # because original_question is missing
        CuriosityEngine._conversations.clear()

    def test_max_turns_is_3(self) -> None:
        """The _MAX_TURNS constant must be exactly 3."""
        assert CuriosityEngine._MAX_TURNS == 3


# ============================================================
# Acceptance Criterion 4 — signal created after conversation
# ============================================================

class TestSignalCreated:
    """After the conversation closes, a human_context signal must be created."""

    def test_close_returns_signal_object(self) -> None:
        """_close_conversation must return a signal object."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        CuriosityEngine._conversations.clear()
        c.follow_up("cq-sig-1", "A1", original_question="Q",
                    question_type="unmeasured_domain", domain="payments")
        c.follow_up("cq-sig-1", "A2")
        result = c.follow_up("cq-sig-1", "A3")
        assert result["signal_created"] is True
        assert "signal" in result  # the raw ExecutionSignal object
        sig = result["signal"]
        assert sig.type == SignalType.DECISION_SIGNAL
        assert sig.metadata.get("kind") == "human_context"
        assert sig.metadata.get("domain") == "payments"
        assert sig.metadata.get("question_type") == "unmeasured_domain"
        assert sig.metadata.get("turn_count") == 3
        assert "understanding" in sig.metadata
        assert "A1" in sig.metadata["understanding"]
        assert "A2" in sig.metadata["understanding"]
        assert "A3" in sig.metadata["understanding"]
        CuriosityEngine._conversations.clear()

    def test_signal_metadata_captures_full_conversation(self) -> None:
        """The signal metadata must contain all 3 turns of Q&A."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        CuriosityEngine._conversations.clear()
        c.follow_up("cq-sig-2", "First answer", original_question="The original Q",
                    question_type="unmeasured_domain", domain="payments")
        c.follow_up("cq-sig-2", "Second answer")
        result = c.follow_up("cq-sig-2", "Third answer")
        sig = result["signal"]
        turns = sig.metadata["turns"]
        assert len(turns) == 3
        assert turns[0]["answer"] == "First answer"
        assert turns[1]["answer"] == "Second answer"
        assert turns[2]["answer"] == "Third answer"
        assert turns[0]["question"] == "The original Q"
        CuriosityEngine._conversations.clear()


# ============================================================
# API endpoint — POST /api/oem/curiosity/follow-up
# ============================================================

class TestFollowUpAPIEndpoint:
    """The POST /api/oem/curiosity/follow-up endpoint must work end-to-end."""

    def test_api_turn_1_returns_follow_up(self, client) -> None:
        """Turn 1 via API must return 200 with a follow_up_question."""
        CuriosityEngine._conversations.clear()
        r = client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-api-1",
            "answer": "We lack the tooling",
            "original_question": "Why is this domain unmeasured?",
            "question_type": "unmeasured_domain",
            "domain": "payments",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["understanding_updated"] is False
        assert data["signal_created"] is False
        assert "follow_up_question" in data
        assert data["turn"] == 2
        CuriosityEngine._conversations.clear()

    def test_api_full_3_turn_conversation(self, client) -> None:
        """A full 3-turn conversation via API must close with understanding_updated."""
        CuriosityEngine._conversations.clear()
        # Turn 1
        r1 = client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-api-2",
            "answer": "We need Datadog",
            "original_question": "Why is payments unmeasured?",
            "question_type": "unmeasured_domain",
            "domain": "payments",
        })
        assert r1.status_code == 200
        assert r1.json()["understanding_updated"] is False

        # Turn 2
        r2 = client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-api-2",
            "answer": "It is a tooling gap",
        })
        assert r2.status_code == 200
        assert r2.json()["understanding_updated"] is False

        # Turn 3 — should close
        r3 = client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-api-2",
            "answer": "If unmeasured, we miss payment failures",
        })
        assert r3.status_code == 200
        data3 = r3.json()
        assert data3["understanding_updated"] is True
        assert data3["signal_created"] is True
        assert "signal_id" in data3
        assert "summary" in data3
        # The raw signal object should NOT be in the API response (not JSON-serializable)
        assert "signal" not in data3
        CuriosityEngine._conversations.clear()

    def test_api_missing_question_id_returns_400(self, client) -> None:
        """Missing question_id must return 400."""
        r = client.post("/api/oem/curiosity/follow-up", json={
            "answer": "some answer",
        })
        assert r.status_code == 400

    def test_api_missing_answer_returns_400(self, client) -> None:
        """Missing answer must return 400."""
        r = client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-api-3",
        })
        assert r.status_code == 400


# ============================================================
# Acceptance Criterion 4 (extended) — signal appears in model after API call
# ============================================================

class TestSignalIngestedIntoModel:
    """After the API closes a conversation, the signal must be in the model."""

    def test_signal_count_increases_after_conversation(self, client) -> None:
        """The OEM's signal count must increase after a conversation closes."""
        CuriosityEngine._conversations.clear()
        # Get the initial state — signal count is in summary.signals_processed
        r0 = client.get("/api/oem/state")
        initial_count = r0.json().get("summary", {}).get("signals_processed", 0)

        # Run a full 3-turn conversation
        client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-ingest-1",
            "answer": "A1",
            "original_question": "Q",
            "question_type": "unmeasured_domain",
            "domain": "test_domain",
        })
        client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-ingest-1",
            "answer": "A2",
        })
        client.post("/api/oem/curiosity/follow-up", json={
            "question_id": "cq-ingest-1",
            "answer": "A3",
        })

        # Get the new state
        r1 = client.get("/api/oem/state")
        new_count = r1.json().get("summary", {}).get("signals_processed", 0)
        assert new_count > initial_count, (
            f"Signal count did not increase after conversation. "
            f"Before: {initial_count}, After: {new_count}"
        )
        CuriosityEngine._conversations.clear()


# ============================================================
# V5 litmus — no new panel
# ============================================================

class TestV5LitmusNoNewPanel:
    """V5 litmus: no new panel. The conversation enhances TODAY, not a new surface."""

    def test_curiosity_module_does_not_create_new_surface(self) -> None:
        """The curiosity module must NOT define a new surface/panel."""
        import maestro_oem.curiosity as mod
        source = open(mod.__file__).read()
        assert "register_surface" not in source
        assert "new_panel" not in source

    def test_today_js_has_conversation_flow(self, client) -> None:
        """today.js must have the conversation flow (input + submitCuriosityAnswer)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        today_path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(today_path):
            pytest.skip(f"today.js not found at {today_path}")
        source = open(today_path).read()
        assert "submitCuriosityAnswer" in source, (
            "today.js missing submitCuriosityAnswer function — conversation flow not wired"
        )
        assert "curiosity-answer-input" in source, (
            "today.js missing the answer input field — conversation flow not rendered"
        )
        assert "Maestro has questions" in source, (
            "today.js missing 'Maestro has questions' header (was 'Maestro is curious')"
        )
        assert "/curiosity/follow-up" in source, (
            "today.js doesn't POST to /curiosity/follow-up"
        )

    def test_routes_oem_has_follow_up_endpoint(self) -> None:
        """routes/oem.py must define the POST /curiosity/follow-up endpoint."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert "@router.post(\"/curiosity/follow-up\")" in source, (
            "routes/oem.py missing POST /curiosity/follow-up endpoint"
        )
        assert "follow_up" in source

    def test_generate_assigns_question_ids(self) -> None:
        """generate() must assign question_id to each question (needed for conversation tracking)."""
        engine = OEMEngine()
        c = CuriosityEngine(engine.get_model(), [])
        result = c.generate()
        # Even with no questions, the structure should be valid
        for q in result.get("questions", []):
            assert "question_id" in q, (
                f"Question missing question_id (needed for conversation tracking): {q}"
            )
            assert q["question_id"].startswith("cq-"), (
                f"question_id should start with 'cq-': {q['question_id']}"
            )
