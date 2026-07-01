"""
V8 Upgrade #1 — Organizational Explanations. Regression tests.

Acceptance criteria (from the V8 spec):
  1. GET /api/oem/explain?q=Why+are+engineering+estimates+always+wrong
     returns a multi-step causal explanation (3+ steps, each with
     evidence_count + confidence).
  2. Each step references real model data (not hardcoded).
  3. ASK v2 renders the explanation as a visual chain. (Frontend —
     covered by static checks + cognitive-surfaces Playwright suite.)
  4. Every confidence score in the UI has a "Why?" link. (Frontend —
     covered by static checks.)
  5. V5 litmus: no new panel — enhances ASK v2 + existing confidence
     displays.
  6. V8 litmus: does this make the customer say "Maestro understands
     our company"? YES — explanations are the proof of understanding.

These tests cover criteria 1, 2, and 5 (no new panel) at the backend
level. Frontend criteria 3, 4 are covered by static file checks and the
existing Playwright suite.
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from maestro_oem import OEMEngine
from maestro_oem.explanations import ExplanationEngine
from maestro_oem.signal import ExecutionSignal, SignalType


# Fixture — build the FastAPI app with demo seed, matching the pattern
# in maestro_api/tests/test_oem_routes.py.
@pytest.fixture(scope="module")
def client():
    """Build the FastAPI app with the OEM initialized (demo seed loaded)."""
    # test file is at backend/maestro_oem/tests/test_v8_explanations.py
    # app root (containing app.html, static/) is parents[3]
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_v8_explanations_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# Test data builders
# ============================================================

def _make_signal(signal_type: SignalType, actor: str = "u@acme.com",
                 artifact: str = "X-1", domain: str = "engineering") -> ExecutionSignal:
    return ExecutionSignal(
        type=signal_type,
        timestamp=datetime.now(timezone.utc),
        actor=actor,
        artifact=artifact,
        metadata={"domain": domain},
    )


def _build_model_with_signals():
    """Build an OEM with realistic signals that produce a 5-step estimate chain."""
    signals = []
    # 5 PRs opened across 2 domains, 1 merged, 1 reviewed
    signals.append(_make_signal(SignalType.PR_OPENED, actor="priya.m@acme.com", artifact="PR-1", domain="payments"))
    signals.append(_make_signal(SignalType.PR_OPENED, actor="priya.m@acme.com", artifact="PR-2", domain="payments"))
    signals.append(_make_signal(SignalType.PR_OPENED, actor="raj.k@acme.com", artifact="PR-3", domain="architecture"))
    signals.append(_make_signal(SignalType.PR_OPENED, actor="priya.m@acme.com", artifact="PR-4", domain="payments"))
    signals.append(_make_signal(SignalType.PR_OPENED, actor="raj.k@acme.com", artifact="PR-5", domain="architecture"))
    signals.append(_make_signal(SignalType.PR_REVIEWED, actor="raj.k@acme.com", artifact="PR-1", domain="payments"))
    signals.append(_make_signal(SignalType.PR_MERGED, actor="priya.m@acme.com", artifact="PR-1", domain="payments"))
    # Blocked transitions
    signals.append(_make_signal(SignalType.ISSUE_TRANSITIONED, actor="qa.lead@acme.com", artifact="ISS-1", domain="qa"))
    signals.append(_make_signal(SignalType.ISSUE_TRANSITIONED, actor="eng.lead@acme.com", artifact="ISS-2", domain="architecture"))

    engine = OEMEngine()
    for s in signals:
        engine.ingest([s])
    return engine.get_model(), signals


# ============================================================
# Acceptance Criterion 1 — 3+ steps, each with evidence_count + confidence
# ============================================================

class TestExplanationChainStructure:
    """The explanation must be a multi-step chain with structured steps."""

    def test_estimate_question_returns_3_plus_steps(self) -> None:
        """'Why are engineering estimates always wrong?' must return 3+ steps."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        assert result["step_count"] >= 3, (
            f"Expected 3+ steps, got {result['step_count']}. "
            f"V8 spec requires multi-step causal explanation."
        )

    def test_each_step_has_evidence_count_and_confidence(self) -> None:
        """Every step must have evidence_count (int) and confidence (float 0..1)."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        for step in result["steps"]:
            assert "evidence_count" in step, f"Step {step.get('step')} missing evidence_count"
            assert isinstance(step["evidence_count"], int)
            assert step["evidence_count"] >= 0
            assert "confidence" in step, f"Step {step.get('step')} missing confidence"
            assert isinstance(step["confidence"], (int, float))
            assert 0.0 <= step["confidence"] <= 1.0, (
                f"Step {step.get('step')} confidence {step['confidence']} out of [0,1] range"
            )

    def test_each_step_has_label_and_narrative(self) -> None:
        """Every step must have a label and a narrative (not just numbers)."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        for step in result["steps"]:
            assert step.get("label"), f"Step {step.get('step')} missing label"
            assert step.get("narrative"), f"Step {step.get('step')} missing narrative"
            assert len(step["narrative"]) > 20, (
                f"Step {step.get('step')} narrative too short: {step['narrative']}"
            )

    def test_steps_are_sequentially_numbered(self) -> None:
        """Steps must be numbered 1, 2, 3, ... in order."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        step_numbers = [s["step"] for s in result["steps"]]
        assert step_numbers == list(range(1, len(step_numbers) + 1)), (
            f"Steps not sequentially numbered: {step_numbers}"
        )

    def test_overall_confidence_and_total_evidence_computed(self) -> None:
        """The response must include overall_confidence and total_evidence."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        assert "overall_confidence" in result
        assert 0.0 <= result["overall_confidence"] <= 1.0
        assert "total_evidence" in result
        assert result["total_evidence"] == sum(s["evidence_count"] for s in result["steps"])


# ============================================================
# Acceptance Criterion 2 — references real model data (not hardcoded)
# ============================================================

class TestExplanationReferencesRealModelData:
    """Each step must reference real model data — no hardcoded content."""

    def test_steps_reference_real_signal_counts(self) -> None:
        """The PR volume step must reflect actual PR_OPENED count from signals."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        # Step 1 (PR volume) must cite the actual PR count (5 in our test data)
        pr_step = next((s for s in result["steps"] if "PR volume" in s["label"]), None)
        assert pr_step is not None, "Missing 'PR volume' step"
        assert pr_step["evidence_count"] == 5, (
            f"PR volume step should cite 5 PRs (from test data), got {pr_step['evidence_count']}"
        )
        # The narrative must contain the actual count
        assert "5" in pr_step["narrative"], (
            f"PR volume narrative must contain actual count '5': {pr_step['narrative']}"
        )

    def test_steps_reference_real_domain_holders(self) -> None:
        """The architecture ownership step must cite real domain holders from the model."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        # Find the architecture ownership step
        arch_step = next((s for s in result["steps"] if "Architecture" in s["label"]), None)
        assert arch_step is not None, "Missing 'Architecture ownership' step"
        # The narrative must reference a real actor from the test signals
        assert "raj.k@acme.com" in arch_step["narrative"], (
            f"Architecture step must reference real domain holder 'raj.k@acme.com': {arch_step['narrative']}"
        )

    def test_sources_list_references_model_entities(self) -> None:
        """Each step's sources list must reference model entities (signals.*, knowledge.*, law.*)."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are engineering estimates always wrong?")

        all_sources = []
        for step in result["steps"]:
            all_sources.extend(step.get("sources", []))
        assert len(all_sources) >= 3, (
            f"Expected 3+ source references across steps, got {len(all_sources)}"
        )
        # Sources must reference real model entity types
        source_text = " ".join(all_sources)
        assert "signals." in source_text or "knowledge." in source_text, (
            f"Sources must reference signals.* or knowledge.* entities: {all_sources}"
        )

    def test_different_inputs_produce_different_chains(self) -> None:
        """Different questions must produce different chains (not hardcoded templates)."""
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)

        estimate_result = engine.explain("Why are engineering estimates always wrong?")
        velocity_result = engine.explain("Why has organizational velocity dropped?")

        # Different outcomes
        assert estimate_result["outcome"] != velocity_result["outcome"]
        # Different step labels (at least one step differs)
        estimate_labels = {s["label"] for s in estimate_result["steps"]}
        velocity_labels = {s["label"] for s in velocity_result["steps"]}
        assert estimate_labels != velocity_labels, (
            "Different questions produced identical chains — content is hardcoded."
        )


# ============================================================
# Honesty — empty model returns no fabricated chain
# ============================================================

class TestExplanationHonesty:
    """V5 honesty rule: no fabricated content. Empty model = honest 'I don't know'."""

    def test_empty_model_returns_no_steps(self) -> None:
        """An empty model must return 0 steps with an honest limitation."""
        engine = OEMEngine()
        model = engine.get_model()
        ex = ExplanationEngine(model, [])
        result = ex.explain("Why are engineering estimates always wrong?")

        assert result["step_count"] == 0
        assert result["honest_limitation"] is not None
        assert "don't have enough" in result["honest_limitation"].lower() or "insufficient" in result["honest_limitation"].lower()

    def test_non_why_question_returns_honest_redirect(self) -> None:
        """A non-'why' question must be honestly redirected, not fabricated."""
        engine = OEMEngine()
        model = engine.get_model()
        ex = ExplanationEngine(model, [])
        result = ex.explain("What is the weather?")

        assert result["step_count"] == 0
        assert result["honest_limitation"] is not None
        assert "why" in result["honest_limitation"].lower()

    def test_unknown_outcome_returns_honest_redirect(self) -> None:
        """A 'why' question about an unknown outcome must be honestly redirected."""
        engine = OEMEngine()
        model = engine.get_model()
        ex = ExplanationEngine(model, [])
        result = ex.explain("Why is the sky blue?")

        assert result["step_count"] == 0
        # Should list the outcomes the engine CAN explain
        assert "estimate" in result["honest_limitation"].lower() or "velocity" in result["honest_limitation"].lower()


# ============================================================
# Outcome coverage — all 5 outcome templates work
# ============================================================

class TestOutcomeCoverage:
    """All 5 outcome templates must produce chains when given real data."""

    def test_velocity_question_returns_chain(self) -> None:
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why has organizational velocity dropped?")
        assert result["outcome"] == "velocity_drop"
        assert result["step_count"] >= 3

    def test_bottleneck_question_returns_chain(self) -> None:
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why is everything bottlenecked?")
        assert result["outcome"] == "bottleneck"
        assert result["step_count"] >= 3

    def test_incident_question_returns_chain(self) -> None:
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are incidents occurring?")
        assert result["outcome"] == "incident"
        assert result["step_count"] >= 3

    def test_attrition_question_returns_chain(self) -> None:
        model, signals = _build_model_with_signals()
        engine = ExplanationEngine(model, signals)
        result = engine.explain("Why are people leaving?")
        assert result["outcome"] == "attrition"
        assert result["step_count"] >= 3


# ============================================================
# API endpoint — /api/oem/explain
# ============================================================

class TestExplainAPIEndpoint:
    """The /api/oem/explain endpoint must work end-to-end."""

    def test_explain_endpoint_returns_200(self, client) -> None:
        """GET /api/oem/explain?q=... must return 200 with a valid chain."""
        r = client.get("/api/oem/explain", params={"q": "Why are engineering estimates always wrong?"})
        assert r.status_code == 200
        data = r.json()
        assert "question" in data
        assert "steps" in data
        assert "step_count" in data
        assert "overall_confidence" in data
        assert "total_evidence" in data

    def test_explain_endpoint_returns_chain_with_demo_seed(self, client) -> None:
        """With the demo seed loaded, the endpoint must return 3+ steps."""
        r = client.get("/api/oem/explain", params={"q": "Why are engineering estimates always wrong?"})
        data = r.json()
        assert data["step_count"] >= 3, (
            f"Demo seed should produce 3+ steps, got {data['step_count']}"
        )

    def test_explain_endpoint_requires_q_param(self, client) -> None:
        """The endpoint must require the q parameter (422 if missing)."""
        r = client.get("/api/oem/explain")
        assert r.status_code == 422  # FastAPI validation error


# ============================================================
# V5 litmus — no new panel (enhances existing surfaces only)
# ============================================================

class TestV5LitmusNoNewPanel:
    """V5 litmus: no new panel. The explanation enhances ASK v2 + confidence displays."""

    def test_explanation_module_does_not_create_new_surface(self) -> None:
        """The explanations module must NOT define a new surface/panel."""
        import maestro_oem.explanations as mod
        source = open(mod.__file__).read()
        # The module must not define surface/panel registration
        assert "register_surface" not in source
        assert "new_panel" not in source

    def test_ask_v2_routes_why_questions_to_explain(self, client) -> None:
        """ASK v2 (static/js/ask_v2.js) must route 'why' questions to /explain."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        ask_v2_path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        if not os.path.exists(ask_v2_path):
            pytest.skip(f"ask_v2.js not found at {ask_v2_path} (frontend not in this test env)")
        source = open(ask_v2_path).read()
        assert "/explain" in source, "ask_v2.js does not route to /explain endpoint"
        assert "renderExplanationAnswer" in source, "ask_v2.js missing renderExplanationAnswer function"
        assert "explanation-chain" in source, "ask_v2.js missing explanation-chain CSS class"

    def test_core_js_has_why_link_helper(self, client) -> None:
        """core.js must define formatConfidenceWithWhy + askWhy helpers."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        core_path = os.path.join(app_dir, "static", "js", "core.js")
        if not os.path.exists(core_path):
            pytest.skip(f"core.js not found at {core_path}")
        source = open(core_path).read()
        assert "formatConfidenceWithWhy" in source, "core.js missing formatConfidenceWithWhy"
        assert "askWhy" in source, "core.js missing askWhy"
        assert "buildWhyQuestion" in source, "core.js missing buildWhyQuestion"

    def test_home_renderers_uses_why_links(self, client) -> None:
        """home_renderers.js must use formatConfidenceWithWhy on recommendations + laws."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        renderers_path = os.path.join(app_dir, "static", "js", "home_renderers.js")
        if not os.path.exists(renderers_path):
            pytest.skip(f"home_renderers.js not found")
        source = open(renderers_path).read()
        assert "formatConfidenceWithWhy" in source, (
            "home_renderers.js does not use formatConfidenceWithWhy — 'Why?' links missing on confidence displays"
        )

    def test_drill_down_modal_uses_why_links(self, client) -> None:
        """drill_down_modal.js must use formatConfidenceWithWhy on prediction confidence."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        modal_path = os.path.join(app_dir, "static", "js", "drill_down_modal.js")
        if not os.path.exists(modal_path):
            pytest.skip(f"drill_down_modal.js not found")
        source = open(modal_path).read()
        assert "formatConfidenceWithWhy" in source, (
            "drill_down_modal.js does not use formatConfidenceWithWhy — 'Why?' links missing on prediction confidence"
        )
