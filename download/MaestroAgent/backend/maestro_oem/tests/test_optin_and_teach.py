"""
V8 P1-2 Fix + P2-3 — Auto-Execute Opt-In + Customer Teaching. Tests.

Tests the Round-35 audit fix (auto-execute requires BOTH eligibility
AND explicit opt-in) and the P2-3 Customer-Initiated Teaching endpoint.
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
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_optin_teach_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_stores():
    from maestro_oem.trust_ledger import TrustLedger
    from maestro_oem.user_settings import UserSettings
    from maestro_oem.writeback import WriteBackStore
    TrustLedger.clear()
    UserSettings.clear()
    WriteBackStore.clear()
    yield
    TrustLedger.clear()
    UserSettings.clear()
    WriteBackStore.clear()


# ============================================================
# P1-2 Fix: Auto-Execute Opt-In
# ============================================================

class TestAutoExecuteOptIn:
    """Auto-execute requires BOTH eligibility AND explicit opt-in."""

    def test_opt_in_default_disabled(self, client) -> None:
        """Auto-execute opt-in must default to disabled."""
        from maestro_oem.user_settings import UserSettings
        assert not UserSettings.is_auto_execute_enabled("anyone", "slack", "post_message")

    def test_requires_opt_in_even_when_eligible(self, client) -> None:
        """Even when eligible (trust >= 10), auto-execute must require opt-in."""
        from maestro_oem.trust_ledger import TrustLedger
        # Give the user 10 successful approvals
        for i in range(10):
            TrustLedger.record("aid", "slack", "post_message", "ceo@acme.com", "success")
        # Try auto-execute WITHOUT opting in
        r = client.post("/api/oem/writeback/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "params": {"channel": "general", "text": "test"},
            "user": "ceo@acme.com",
        })
        data = r.json()
        assert data["status"] == "requires_opt_in", (
            "Auto-execute should require opt-in even when eligible. "
            f"Got: {data['status']}"
        )
        assert data["auto"] is False
        assert data["eligible"] is True

    def test_auto_execute_after_opt_in_and_eligibility(self, client) -> None:
        """Auto-execute works only after BOTH opting in AND being eligible."""
        from maestro_oem.trust_ledger import TrustLedger
        # 10 successes
        for i in range(10):
            TrustLedger.record("aid", "slack", "post_message", "ceo@acme.com", "success")
        # Opt in
        client.post("/api/oem/settings/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "enabled": True, "user": "ceo@acme.com",
        })
        # Now auto-execute should work
        r = client.post("/api/oem/writeback/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "params": {"channel": "general", "text": "auto test"},
            "user": "ceo@acme.com",
        })
        data = r.json()
        assert data["status"] == "executed"
        assert data.get("auto") is True

    def test_opt_in_without_eligibility_still_fails(self, client) -> None:
        """Opting in without enough trust must still fail."""
        # Opt in but no trust history
        client.post("/api/oem/settings/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "enabled": True, "user": "newuser@acme.com",
        })
        r = client.post("/api/oem/writeback/auto-execute", json={
            "provider": "slack", "action_type": "post_message",
            "params": {"channel": "general", "text": "test"},
            "user": "newuser@acme.com",
        })
        data = r.json()
        assert data["status"] == "requires_manual_approval"

    def test_settings_endpoints(self, client) -> None:
        """POST and GET /settings/auto-execute must work."""
        # Set
        r1 = client.post("/api/oem/settings/auto-execute", json={
            "provider": "jira", "action_type": "create_issue",
            "enabled": True, "user": "ceo@acme.com",
        })
        assert r1.status_code == 200
        assert r1.json()["auto_execute_enabled"]["jira:create_issue"] is True
        # Get
        r2 = client.get("/api/oem/settings/auto-execute", params={"user": "ceo@acme.com"})
        assert r2.status_code == 200
        data = r2.json()
        assert "action_types" in data
        assert len(data["action_types"]) >= 1

    def test_docstring_matches_code(self) -> None:
        """The docstring must accurately describe the two-check flow."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        # The docstring must mention BOTH checks
        assert "Eligibility" in source and "Explicit opt-in" in source
        # The code must have both checks
        assert "is_auto_execute_eligible" in source
        assert "is_auto_execute_enabled" in source
        assert "requires_opt_in" in source


# ============================================================
# P2-3: Customer-Initiated Teaching
# ============================================================

class TestCustomerTeaching:
    """The customer can teach Maestro in free text."""

    def test_teach_returns_200(self, client) -> None:
        r = client.post("/api/oem/teach", json={
            "text": "Legal always slows down OAuth approvals because Sarah needs to review every scope change.",
            "actor": "ceo@acme.com",
        })
        assert r.status_code == 200

    def test_teach_returns_learned_and_signal_id(self, client) -> None:
        r = client.post("/api/oem/teach", json={
            "text": "Engineering never deploys on Fridays because of the incident last quarter.",
            "actor": "ceo@acme.com",
        })
        data = r.json()
        assert "learned" in data
        assert "signal_id" in data
        assert "confirmation" in data
        assert data["editable"] is True

    def test_teach_extracts_domains(self, client) -> None:
        """Teaching must extract domain keywords from the text."""
        r = client.post("/api/oem/teach", json={
            "text": "The OAuth security review process is blocking deployments.",
            "actor": "ceo@acme.com",
        })
        data = r.json()
        learned = data["learned"]
        assert "domains" in learned
        # Should find oauth, security, deployment
        domains_lower = [d.lower() for d in learned["domains"]]
        assert "oauth" in domains_lower or "security" in domains_lower

    def test_teach_extracts_causal_patterns(self, client) -> None:
        """Teaching must extract causal patterns ('because', 'always', 'never')."""
        r = client.post("/api/oem/teach", json={
            "text": "Deployments always fail because the QA gate is too strict.",
            "actor": "ceo@acme.com",
        })
        data = r.json()
        learned = data["learned"]
        assert "causal_patterns" in learned
        assert len(learned["causal_patterns"]) > 0

    def test_teach_extracts_emails(self, client) -> None:
        """Teaching must extract email addresses as people."""
        r = client.post("/api/oem/teach", json={
            "text": "Sarah@acme.com is the bottleneck for all legal reviews.",
            "actor": "ceo@acme.com",
        })
        data = r.json()
        learned = data["learned"]
        assert "people" in learned
        assert len(learned["people"]) > 0

    def test_teach_requires_text(self, client) -> None:
        """POST /teach without text must return 400."""
        r = client.post("/api/oem/teach", json={"text": ""})
        assert r.status_code == 400

    def test_teach_creates_signal(self, client) -> None:
        """Teaching must create a human_context signal in the model."""
        from maestro_api.oem_state import oem_state
        signals_before = len(oem_state.signals)
        client.post("/api/oem/teach", json={
            "text": "Payments team needs to coordinate with Legal before any OAuth scope change.",
            "actor": "ceo@acme.com",
        })
        signals_after = len(oem_state.signals)
        assert signals_after > signals_before, "Teaching did not create a signal"

    def test_teach_endpoint_exists(self) -> None:
        """routes/oem.py must have the /teach endpoint."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert '@router.post("/teach")' in source
        assert "_extract_knowledge_from_text" in source

    def test_teach_confirmation_is_editable(self, client) -> None:
        """The teaching response must be editable (customer can correct)."""
        r = client.post("/api/oem/teach", json={
            "text": "Always review PRs within 24 hours.",
            "actor": "ceo@acme.com",
        })
        data = r.json()
        assert data["editable"] is True
        assert "confirmation" in data
        assert "Is this correct?" in data["confirmation"] or "learned" in data["confirmation"].lower()
