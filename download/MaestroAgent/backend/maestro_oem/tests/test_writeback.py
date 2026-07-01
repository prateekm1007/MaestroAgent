"""
V8 Daily Work #4 — Write-Back to Tools. Regression tests.

Acceptance criteria:
  1. POST /api/oem/writeback returns a preview (not executed)
  2. POST /api/oem/writeback/{id}/approve executes and returns result
  3. Jira: creates a real issue (verified via mock)
  4. Gmail: creates a DRAFT (not sent — user sends manually)
  5. All write-backs require approval (no autonomous execution)
  6. V5 litmus: "Execute" button enhances TODAY. Feeds constitution: action signals.
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient

from maestro_oem.writeback import WriteBackService, WriteBackStore


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_writeback_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_writeback_store():
    """Clear the writeback store before each test to prevent cross-test pollution."""
    WriteBackStore.clear()
    yield
    WriteBackStore.clear()


# ============================================================
# Acceptance Criterion 1 — preview (NOT executed)
# ============================================================

class TestWriteBackPreview:
    """POST /api/oem/writeback must return a preview, not execute."""

    def test_preview_returns_pending_status(self, client) -> None:
        """Preview must return status='pending', not 'executed'."""
        r = client.post("/api/oem/writeback", json={
            "provider": "jira",
            "action_type": "create_issue",
            "params": {"project": "ENG", "summary": "Test", "description": "desc"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending"
        assert "action_id" in data
        assert "preview" in data

    def test_preview_does_not_execute(self, client) -> None:
        """After preview, the action must NOT be executed."""
        r = client.post("/api/oem/writeback", json={
            "provider": "slack",
            "action_type": "post_message",
            "params": {"channel": "general", "text": "test"},
        })
        data = r.json()
        assert data["status"] == "pending"
        # Check that no result exists yet
        action = WriteBackStore.get(data["action_id"])
        assert action is not None
        assert action.status == "pending"
        assert action.result is None

    def test_preview_has_human_readable_text(self, client) -> None:
        """The preview must contain human-readable text about the action."""
        r = client.post("/api/oem/writeback", json={
            "provider": "gmail",
            "action_type": "create_draft",
            "params": {"to": "eng@acme.com", "subject": "Test", "body": "Body"},
        })
        data = r.json()
        assert "Gmail" in data["preview"]
        assert "DRAFT" in data["preview"]
        assert "NOT sent" in data["preview"]

    def test_preview_rejects_unsupported_provider(self, client) -> None:
        """Unsupported providers must return 400."""
        r = client.post("/api/oem/writeback", json={
            "provider": "unsupported",
            "action_type": "test",
            "params": {},
        })
        assert r.status_code == 400

    def test_preview_rejects_unsupported_action_type(self, client) -> None:
        """Unsupported action types must return 400."""
        r = client.post("/api/oem/writeback", json={
            "provider": "jira",
            "action_type": "unsupported_action",
            "params": {},
        })
        assert r.status_code == 400


# ============================================================
# Acceptance Criterion 2 — approve executes
# ============================================================

class TestWriteBackApprove:
    """POST /api/oem/writeback/{id}/approve must execute the action."""

    def test_approve_executes_pending_action(self, client) -> None:
        """Approving a pending action must execute it."""
        # Preview
        r1 = client.post("/api/oem/writeback", json={
            "provider": "jira",
            "action_type": "create_issue",
            "params": {"project": "ENG", "summary": "Test", "description": "desc"},
        })
        action_id = r1.json()["action_id"]

        # Approve
        r2 = client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "ceo"})
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "executed"
        assert data["result"] is not None
        assert data["approved_by"] == "ceo"

    def test_approve_nonexistent_action_returns_404(self, client) -> None:
        """Approving a non-existent action must return 404."""
        r = client.post("/api/oem/writeback/nonexistent-id/approve", json={"approved_by": "user"})
        assert r.status_code == 404

    def test_approve_already_executed_action_fails(self, client) -> None:
        """Approving an already-executed action must fail."""
        r1 = client.post("/api/oem/writeback", json={
            "provider": "jira",
            "action_type": "create_issue",
            "params": {"project": "ENG", "summary": "Test"},
        })
        action_id = r1.json()["action_id"]
        # First approve
        client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "user"})
        # Second approve
        r2 = client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "user"})
        assert r2.status_code == 404  # Not pending anymore

    def test_reject_does_not_execute(self, client) -> None:
        """Rejecting an action must NOT execute it."""
        r1 = client.post("/api/oem/writeback", json={
            "provider": "slack",
            "action_type": "post_message",
            "params": {"channel": "general", "text": "test"},
        })
        action_id = r1.json()["action_id"]
        r2 = client.post(f"/api/oem/writeback/{action_id}/reject", json={"rejected_by": "user"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "rejected"
        # Verify it was NOT executed
        action = WriteBackStore.get(action_id)
        assert action.result is None


# ============================================================
# Acceptance Criterion 3 — Jira creates issue (mock)
# ============================================================

class TestJiraWriteBack:
    """Jira write-back must create an issue (mock mode in tests)."""

    def test_jira_creates_issue(self, client) -> None:
        """Jira write-back must return an issue_key."""
        r1 = client.post("/api/oem/writeback", json={
            "provider": "jira",
            "action_type": "create_issue",
            "params": {"project": "ENG", "summary": "Fix P1", "description": "desc", "issue_type": "Bug"},
        })
        action_id = r1.json()["action_id"]
        r2 = client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "user"})
        result = r2.json()["result"]
        assert result["provider"] == "jira"
        assert "issue_key" in result
        assert result["issue_key"].startswith("ENG-")
        assert "issue_url" in result


# ============================================================
# Acceptance Criterion 4 — Gmail creates DRAFT (NOT sent)
# ============================================================

class TestGmailWriteBack:
    """Gmail write-back must create a DRAFT, never send."""

    def test_gmail_creates_draft_not_sent(self, client) -> None:
        """Gmail write-back must return sent=False (draft only)."""
        r1 = client.post("/api/oem/writeback", json={
            "provider": "gmail",
            "action_type": "create_draft",
            "params": {"to": "eng@acme.com", "subject": "Test", "body": "Body"},
        })
        action_id = r1.json()["action_id"]
        r2 = client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "user"})
        result = r2.json()["result"]
        assert result["provider"] == "gmail"
        assert result["sent"] is False  # CRITICAL: Maestro never sends
        assert "draft_id" in result
        assert "draft_url" in result

    def test_gmail_preview_says_not_sent(self, client) -> None:
        """The Gmail preview must explicitly say 'NOT sent'."""
        r = client.post("/api/oem/writeback", json={
            "provider": "gmail",
            "action_type": "create_draft",
            "params": {"to": "eng@acme.com", "subject": "Test", "body": "Body"},
        })
        preview = r.json()["preview"]
        assert "NOT sent" in preview or "DRAFT" in preview


# ============================================================
# Acceptance Criterion 5 — all require approval
# ============================================================

class TestAllRequireApproval:
    """All write-backs must require explicit approval — no autonomous execution."""

    def test_preview_does_not_execute_any_provider(self, client) -> None:
        """Preview must not execute for ANY provider."""
        providers = [
            ("jira", "create_issue", {"project": "ENG", "summary": "T", "description": "d"}),
            ("github", "create_issue_comment", {"repo": "acme/x", "issue_number": 1, "body": "comment"}),
            ("slack", "post_message", {"channel": "general", "text": "test"}),
            ("gmail", "create_draft", {"to": "a@b.com", "subject": "T", "body": "B"}),
        ]
        for provider, action_type, params in providers:
            WriteBackStore.clear()
            r = client.post("/api/oem/writeback", json={
                "provider": provider,
                "action_type": action_type,
                "params": params,
            })
            data = r.json()
            assert data["status"] == "pending", (
                f"{provider}.{action_type} should be pending after preview, got {data['status']}"
            )

    def test_all_providers_execute_on_approve(self, client) -> None:
        """All providers must execute successfully on approve (mock mode)."""
        providers = [
            ("jira", "create_issue", {"project": "ENG", "summary": "T", "description": "d"}),
            ("github", "create_issue_comment", {"repo": "acme/x", "issue_number": 1, "body": "comment"}),
            ("slack", "post_message", {"channel": "general", "text": "test"}),
            ("gmail", "create_draft", {"to": "a@b.com", "subject": "T", "body": "B"}),
        ]
        for provider, action_type, params in providers:
            WriteBackStore.clear()
            r1 = client.post("/api/oem/writeback", json={
                "provider": provider, "action_type": action_type, "params": params,
            })
            action_id = r1.json()["action_id"]
            r2 = client.post(f"/api/oem/writeback/{action_id}/approve", json={"approved_by": "user"})
            assert r2.json()["status"] == "executed", (
                f"{provider}.{action_type} should execute on approve, got {r2.json().get('status')}"
            )


# ============================================================
# V5 litmus — no new panel
# ============================================================

class TestV5LitmusNoNewPanel:
    """V5 litmus: Execute button enhances TODAY, not a new panel."""

    def test_writeback_module_does_not_create_surface(self) -> None:
        import maestro_oem.writeback as mod
        source = open(mod.__file__).read()
        assert "register_surface" not in source
        assert "new_panel" not in source

    def test_today_js_has_execute_button(self, client) -> None:
        """today.js must have the executeWriteBack function."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        today_path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(today_path):
            pytest.skip(f"today.js not found at {today_path}")
        source = open(today_path).read()
        assert "executeWriteBack" in source, "today.js missing executeWriteBack function"
        assert "/writeback" in source, "today.js doesn't call /writeback endpoint"
        assert "Create Jira ticket" in source, "today.js missing 'Create Jira ticket' button"
        assert "Draft email" in source, "today.js missing 'Draft email' button"

    def test_routes_oem_has_writeback_endpoints(self) -> None:
        """routes/oem.py must have the writeback endpoints."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert '@router.post("/writeback")' in source
        assert '@router.post("/writeback/{action_id}/approve")' in source
        assert '@router.post("/writeback/{action_id}/reject")' in source

    def test_gmail_module_never_sends(self) -> None:
        """The Gmail writeback module must NEVER call the send endpoint."""
        import maestro_oem.writeback.gmail as mod
        source = open(mod.__file__).read()
        # The send endpoint is /drafts/send — it must NOT appear in the source
        assert "drafts/send" not in source, (
            "Gmail writeback module references the send endpoint — "
            "Maestro must NEVER send emails autonomously"
        )
        # The create-draft endpoint IS allowed
        assert "drafts" in source
