"""
V8 P0 Features — Regression tests.

P0-1: Commitments Due Today in the Briefing
P0-2: Inline "Why?" on Every Briefing Item
P0-3: One-Tap Write-Back in the Briefing
P0-4: Synthesized Natural-Language Answers
P0-5: Push Delivery (Opt-In)
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_p0_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# P0-1: Commitments Due Today in the Briefing
# ============================================================

class TestCommitmentsInBriefing:
    """The briefing must include a commitments block."""

    def test_briefing_has_commitments_field(self, client) -> None:
        r = client.get("/api/oem/ceo-briefing")
        assert r.status_code == 200
        data = r.json()
        assert "commitments" in data, "Briefing missing 'commitments' field"

    def test_commitments_has_required_fields(self, client) -> None:
        r = client.get("/api/oem/ceo-briefing")
        data = r.json()
        c = data["commitments"]
        assert "summary" in c
        assert "commitments" in c
        assert "headline" in c
        assert "overdue_count" in c

    def test_today_js_has_commitments_section(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(path):
            pytest.skip("today.js not found")
        source = open(path).read()
        assert "Commitments due today" in source, "today.js missing 'Commitments due today' section"
        assert "sendCommitmentReminder" in source, "today.js missing sendCommitmentReminder function"


# ============================================================
# P0-2: Inline "Why?" on Every Briefing Item
# ============================================================

class TestInlineWhy:
    """Every briefing item must have a 'Why?' link."""

    def test_today_js_has_showInlineWhy(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(path):
            pytest.skip("today.js not found")
        source = open(path).read()
        assert "showInlineWhy" in source, "today.js missing showInlineWhy function"
        assert "/explain" in source, "today.js doesn't call /explain endpoint"
        assert "why-link" in source, "today.js missing 'why-link' class"

    def test_explain_endpoint_returns_chain(self, client) -> None:
        """The /explain endpoint must return a causal chain for 'why' questions."""
        r = client.get("/api/oem/explain", params={"q": "Why are engineering estimates always wrong?"})
        assert r.status_code == 200
        data = r.json()
        assert "steps" in data


# ============================================================
# P0-3: One-Tap Write-Back in the Briefing
# ============================================================

class TestOneTapWriteBack:
    """Briefing items must have 'Create ticket' and 'Send message' buttons."""

    def test_today_js_has_quickWriteBack(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(path):
            pytest.skip("today.js not found")
        source = open(path).read()
        assert "quickWriteBack" in source, "today.js missing quickWriteBack function"
        assert "approveQuickWriteBack" in source, "today.js missing approveQuickWriteBack function"
        assert "Create ticket" in source, "today.js missing 'Create ticket' button"
        assert "Send message" in source, "today.js missing 'Send message' button"

    def test_writeback_preview_then_approve_flow(self, client) -> None:
        """The write-back flow must be preview → approve (2 taps, never 1)."""
        from maestro_oem.writeback import WriteBackStore
        WriteBackStore.clear()
        # Step 1: Preview
        r1 = client.post("/api/oem/writeback", json={
            "provider": "jira",
            "action_type": "create_issue",
            "params": {"project": "ENG", "summary": "Test", "description": "desc"},
        })
        assert r1.json()["status"] == "pending"
        action_id = r1.json()["action_id"]
        # Step 2: Approve
        r2 = client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "test"})
        assert r2.json()["status"] == "executed"
        WriteBackStore.clear()


# ============================================================
# P0-4: Synthesized Natural-Language Answers
# ============================================================

class TestSynthesizedAnswers:
    """Ask must return a synthesized natural-language answer, not just bullets."""

    def test_ask_returns_synthesized_answer(self, client) -> None:
        r = client.get("/api/oem/ask", params={"q": "who is the bottleneck?"})
        assert r.status_code == 200
        data = r.json()
        assert "synthesized_answer" in data, "Ask response missing 'synthesized_answer'"
        assert isinstance(data["synthesized_answer"], str)
        assert len(data["synthesized_answer"]) > 20

    def test_ask_returns_evidence_detail(self, client) -> None:
        """The bullet-point evidence must still be available as evidence_detail."""
        r = client.get("/api/oem/ask", params={"q": "bottleneck"})
        data = r.json()
        assert "evidence_detail" in data, "Ask response missing 'evidence_detail'"

    def test_synthesized_answer_cites_evidence(self, client) -> None:
        """The synthesized answer must reference at least one law or LO by name."""
        r = client.get("/api/oem/ask", params={"q": "who is the bottleneck?"})
        data = r.json()
        synthesized = data.get("synthesized_answer", "")
        # Should contain a law code (L-XXXX) or "evidence" or "confidence"
        has_evidence = any(kw in synthesized.lower() for kw in ["l-0", "evidence", "confidence", "based on", "pattern"])
        assert has_evidence, f"Synthesized answer doesn't cite evidence: '{synthesized[:100]}'"

    def test_ask_v2_js_renders_synthesized(self, client) -> None:
        """ask_v2.js must render synthesized_answer as primary."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "ask_v2.js")
        if not os.path.exists(path):
            pytest.skip("ask_v2.js not found")
        source = open(path).read()
        assert "synthesized_answer" in source, "ask_v2.js doesn't use synthesized_answer"
        assert "evidence_detail" in source, "ask_v2.js doesn't use evidence_detail"
        assert "Show evidence" in source, "ask_v2.js missing 'Show evidence' collapsible"

    def test_decision_py_has_synthesize_method(self) -> None:
        """decision.py must have _synthesize_answer method."""
        import maestro_oem.decision as mod
        source = open(mod.__file__).read()
        assert "_synthesize_answer" in source, "decision.py missing _synthesize_answer method"


# ============================================================
# P0-5: Push Delivery (Opt-In)
# ============================================================

class TestPushDelivery:
    """Push delivery must be opt-in. Default: disabled."""

    def test_push_settings_default_disabled(self, client) -> None:
        """Default push settings must be disabled."""
        from maestro_oem.push_delivery import PushDeliveryService
        svc = PushDeliveryService()
        settings = svc.get_settings()
        assert settings.enabled is False
        assert settings.channel == "none"

    def test_set_push_settings(self, client) -> None:
        """POST /api/oem/push/settings must set settings."""
        r = client.post("/api/oem/push/settings", json={
            "channel": "slack",
            "time": "08:00",
            "enabled": True,
            "slack_channel": "#general",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["channel"] == "slack"
        assert data["enabled"] is True
        assert data["time"] == "08:00"

    def test_push_settings_validation(self, client) -> None:
        """Invalid channel must return 400."""
        r = client.post("/api/oem/push/settings", json={
            "channel": "invalid",
            "enabled": True,
        })
        assert r.status_code == 400

    def test_push_settings_requires_slack_channel(self, client) -> None:
        """Setting channel=slack without slack_channel must return 400."""
        r = client.post("/api/oem/push/settings", json={
            "channel": "slack",
            "enabled": True,
        })
        assert r.status_code == 400

    def test_push_deliver_disabled_returns_false(self, client) -> None:
        """Delivering when push is disabled must return delivered=False."""
        from maestro_oem.push_delivery import PushDeliveryService
        svc = PushDeliveryService()
        # Reset to defaults
        svc._settings.clear()
        result = svc.deliver_briefing(briefing_data={"one_thing": {}})
        assert result["delivered"] is False

    def test_push_deliver_enabled_returns_true(self, client) -> None:
        """Delivering when push is enabled must return delivered=True."""
        from maestro_oem.push_delivery import PushDeliveryService
        svc = PushDeliveryService()
        svc.set_settings(
            channel="slack",
            enabled=True,
            slack_channel="#general",
        )
        result = svc.deliver_briefing(briefing_data={
            "one_thing": {"title": "Test priority"},
            "overnight": {"summary": "Nothing changed."},
            "commitments": {"summary": "No commitments."},
        })
        assert result["delivered"] is True
        assert result["channel"] == "slack"
        svc._settings.clear()

    def test_push_test_endpoint(self, client) -> None:
        """POST /api/oem/push/test must return a test result."""
        # First set a channel
        client.post("/api/oem/push/settings", json={
            "channel": "email",
            "enabled": True,
            "email_address": "ceo@acme.com",
        })
        r = client.post("/api/oem/push/test")
        assert r.status_code == 200
        data = r.json()
        assert data["delivered"] is True

    def test_push_endpoints_exist(self) -> None:
        """routes/oem.py must have the push endpoints."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert '@router.get("/push/settings")' in source
        assert '@router.post("/push/settings")' in source
        assert '@router.post("/push/test")' in source
        assert '@router.post("/push/deliver")' in source

    def test_push_delivery_module_exists(self) -> None:
        """push_delivery.py must exist and have PushDeliveryService."""
        import maestro_oem.push_delivery as mod
        source = open(mod.__file__).read()
        assert "class PushDeliveryService" in source
        assert "class PushSettings" in source
