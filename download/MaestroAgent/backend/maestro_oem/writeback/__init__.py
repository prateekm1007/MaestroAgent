"""
V8 Daily Work #4 — Write-Back to Tools.

THE gap between "advises" and "does work." Maestro can now create Jira
tickets, draft Gmail emails (NOT send — user sends manually), post Slack
messages, and create GitHub review comments. All gated by approval
(governance mode) — no autonomous execution.

Architecture:
  - WriteBackAction: a pending action with preview + approve flow
  - WriteBackStore: in-memory store of pending actions (keyed by action_id)
  - WriteBackService: orchestrates preview + execute across 4 providers
  - Provider modules (jira, github, slack, gmail): each has preview() + execute()

The flow:
  1. POST /api/oem/writeback with {provider, action_type, params}
     → returns a preview (NOT executed). The action is stored pending.
  2. POST /api/oem/writeback/{action_id}/approve
     → executes the action. Returns the result (e.g. Jira issue key, Slack message timestamp).
  3. POST /api/oem/writeback/{action_id}/reject
     → rejects the action (no execution).

Governance: all write-backs require explicit approval. No autonomous
execution. Gmail ONLY creates drafts — never sends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class WriteBackAction:
    """A pending write-back action awaiting approval.

    Attributes:
        action_id: unique ID for this action
        provider: "jira" | "github" | "slack" | "gmail"
        action_type: "create_issue" | "create_review_comment" | "post_message" | "create_draft"
        params: the parameters for the action (provider-specific)
        preview: a human-readable preview of what the action will do
        status: "pending" | "approved" | "rejected" | "executed" | "failed"
        created_at: ISO timestamp
        approved_by: who approved (set on approve)
        executed_at: when the action was executed (set on execute)
        result: the execution result (set on execute)
        error: error message if execution failed
    """
    action_id: str = field(default_factory=lambda: str(uuid4()))
    provider: str = ""
    action_type: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    preview: str = ""
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: str | None = None
    executed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "provider": self.provider,
            "action_type": self.action_type,
            "params": self.params,
            "preview": self.preview,
            "status": self.status,
            "created_at": self.created_at,
            "approved_by": self.approved_by,
            "executed_at": self.executed_at,
            "result": self.result,
            "error": self.error,
        }


class WriteBackStore:
    """In-memory store of pending write-back actions.

    Actions are stored in memory (not persisted) because they're ephemeral —
    the user previews, approves/rejects, and the action is executed or
    discarded. If the server restarts, pending actions are lost (the user
    re-requests). This is the same pattern as the conversational curiosity
    state.
    """

    _actions: dict[str, WriteBackAction] = {}

    @classmethod
    def store(cls, action: WriteBackAction) -> None:
        cls._actions[action.action_id] = action

    @classmethod
    def get(cls, action_id: str) -> WriteBackAction | None:
        return cls._actions.get(action_id)

    @classmethod
    def list_pending(cls) -> list[WriteBackAction]:
        return [a for a in cls._actions.values() if a.status == "pending"]

    @classmethod
    def list_all(cls) -> list[WriteBackAction]:
        return list(cls._actions.values())

    @classmethod
    def remove(cls, action_id: str) -> None:
        cls._actions.pop(action_id, None)

    @classmethod
    def clear(cls) -> None:
        cls._actions.clear()


class WriteBackService:
    """Orchestrates write-back preview + execute across 4 providers.

    The service is the single entry point for all write-back operations.
    It validates the provider + action_type, generates a preview, stores
    the action pending approval, and executes on approve.
    """

    # Supported providers and their action types
    _SUPPORTED_ACTIONS = {
        "jira": {"create_issue"},
        "github": {"create_review_comment", "create_issue_comment"},
        "slack": {"post_message"},
        "gmail": {"create_draft"},
    }

    def __init__(self, oauth_manager: Any = None, connection_manager: Any = None) -> None:
        self.oauth = oauth_manager
        self.connections = connection_manager

    def preview(
        self,
        provider: str,
        action_type: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a preview of the write-back action (NOT executed).

        Args:
            provider: "jira" | "github" | "slack" | "gmail"
            action_type: the action to perform (provider-specific)
            params: parameters for the action

        Returns:
            {
                action_id: str,
                provider: str,
                action_type: str,
                preview: str,           # human-readable preview
                status: "pending",
                params: dict,           # the params (echoed back)
            }

        Raises:
            ValueError: if provider or action_type is unsupported
        """
        # Validate provider + action_type
        if provider not in self._SUPPORTED_ACTIONS:
            raise ValueError(
                f"Unsupported provider: '{provider}'. Supported: {list(self._SUPPORTED_ACTIONS.keys())}"
            )
        if action_type not in self._SUPPORTED_ACTIONS[provider]:
            raise ValueError(
                f"Unsupported action_type '{action_type}' for provider '{provider}'. "
                f"Supported: {list(self._SUPPORTED_ACTIONS[provider])}"
            )

        # Generate preview text (provider-specific)
        preview_text = self._generate_preview(provider, action_type, params)

        # Store the action pending approval
        action = WriteBackAction(
            provider=provider,
            action_type=action_type,
            params=params,
            preview=preview_text,
            status="pending",
        )
        WriteBackStore.store(action)

        return {
            "action_id": action.action_id,
            "provider": provider,
            "action_type": action_type,
            "preview": preview_text,
            "status": "pending",
            "params": params,
            "message": "Preview generated. Call POST /api/oem/writeback/{action_id}/approve to execute.",
        }

    def approve(self, action_id: str, approved_by: str = "user", auto_execute: bool = False) -> dict[str, Any]:
        """Execute a previously-previewed write-back action.

        Args:
            action_id: the action ID from preview()
            approved_by: who approved the action (for audit)

        Returns:
            {
                action_id: str,
                status: "executed" | "failed",
                result: dict,     # provider-specific result
                error: str | None,
            }

        Raises:
            ValueError: if the action doesn't exist or isn't pending
        """
        action = WriteBackStore.get(action_id)
        if action is None:
            raise ValueError(f"Action not found: {action_id}")
        if action.status != "pending":
            raise ValueError(
                f"Action {action_id} is not pending (current status: {action.status})"
            )

        action.approved_by = approved_by

        try:
            # Execute the action (provider-specific)
            result = self._execute(action)
            action.status = "executed"
            action.executed_at = datetime.now(timezone.utc).isoformat()
            action.result = result
            logger.info(
                "Write-back executed: provider=%s action=%s action_id=%s approved_by=%s",
                action.provider, action.action_type, action_id, approved_by,
            )
            # V8 P1-1 — Record in trust ledger
            try:
                from maestro_oem.trust_ledger import TrustLedger
                TrustLedger.record(
                    action_id=action_id,
                    provider=action.provider,
                    action_type=action.action_type,
                    approver=approved_by,
                    outcome="success",
                    auto=auto_execute,
                )
            except Exception:
                pass
        except Exception as e:
            action.status = "failed"
            action.error = str(e)
            action.executed_at = datetime.now(timezone.utc).isoformat()
            logger.warning(
                "Write-back failed: provider=%s action=%s action_id=%s error=%s",
                action.provider, action.action_type, action_id, e,
            )
            # V8 P1-1 — Record failure in trust ledger
            try:
                from maestro_oem.trust_ledger import TrustLedger
                TrustLedger.record(
                    action_id=action_id,
                    provider=action.provider,
                    action_type=action.action_type,
                    approver=approved_by,
                    outcome="failure",
                    auto=auto_execute,
                )
            except Exception:
                pass

        return action.to_dict()

    def reject(self, action_id: str, rejected_by: str = "user") -> dict[str, Any]:
        """Reject a pending write-back action (no execution)."""
        action = WriteBackStore.get(action_id)
        if action is None:
            raise ValueError(f"Action not found: {action_id}")
        action.status = "rejected"
        action.approved_by = rejected_by
        return action.to_dict()

    def _generate_preview(self, provider: str, action_type: str, params: dict[str, Any]) -> str:
        """Generate a human-readable preview of the action."""
        if provider == "jira":
            return self._preview_jira(action_type, params)
        elif provider == "github":
            return self._preview_github(action_type, params)
        elif provider == "slack":
            return self._preview_slack(action_type, params)
        elif provider == "gmail":
            return self._preview_gmail(action_type, params)
        return f"{provider}.{action_type}: {params}"

    def _preview_jira(self, action_type: str, params: dict[str, Any]) -> str:
        project = params.get("project", "UNKNOWN")
        summary = params.get("summary", "")
        description = params.get("description", "")
        issue_type = params.get("issue_type", "Task")
        return (
            f"Jira — Create {issue_type} in project {project}\n"
            f"Summary: {summary}\n"
            f"Description: {description[:200]}{'...' if len(description) > 200 else ''}\n"
            f"(This will create a real Jira issue when approved.)"
        )

    def _preview_github(self, action_type: str, params: dict[str, Any]) -> str:
        repo = params.get("repo", "")
        pr_number = params.get("pr_number", "")
        body = params.get("body", "")
        if action_type == "create_review_comment":
            return (
                f"GitHub — Create review comment on {repo}#{pr_number}\n"
                f"Comment: {body[:200]}{'...' if len(body) > 200 else ''}\n"
                f"(This will post a real comment when approved.)"
            )
        else:
            issue_number = params.get("issue_number", "")
            return (
                f"GitHub — Create comment on {repo}#{issue_number}\n"
                f"Comment: {body[:200]}{'...' if len(body) > 200 else ''}\n"
                f"(This will post a real comment when approved.)"
            )

    def _preview_slack(self, action_type: str, params: dict[str, Any]) -> str:
        channel = params.get("channel", "")
        text = params.get("text", "")
        return (
            f"Slack — Post message to #{channel}\n"
            f"Message: {text[:200]}{'...' if len(text) > 200 else ''}\n"
            f"(This will post a real message when approved.)"
        )

    def _preview_gmail(self, action_type: str, params: dict[str, Any]) -> str:
        to = params.get("to", "")
        subject = params.get("subject", "")
        body = params.get("body", "")
        return (
            f"Gmail — Create DRAFT email (NOT sent)\n"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"Body: {body[:200]}{'...' if len(body) > 200 else ''}\n"
            f"(This will create a DRAFT when approved. You send it manually.)"
        )

    def _execute(self, action: WriteBackAction) -> dict[str, Any]:
        """Execute the action (provider-specific). Returns the result."""
        # Get OAuth token (if OAuth manager is available)
        token = None
        if self.oauth:
            try:
                token = self.oauth.get_valid_access_token(action.provider)
            except Exception as e:
                logger.warning("Failed to get OAuth token for %s: %s", action.provider, e)
                # In dev/test mode without OAuth, use a mock token
                token = "mock-token-for-testing"

        if action.provider == "jira":
            from maestro_oem.writeback.jira import execute_jira
            return execute_jira(action, token)
        elif action.provider == "github":
            from maestro_oem.writeback.github import execute_github
            return execute_github(action, token)
        elif action.provider == "slack":
            from maestro_oem.writeback.slack import execute_slack
            return execute_slack(action, token)
        elif action.provider == "gmail":
            from maestro_oem.writeback.gmail import execute_gmail
            return execute_gmail(action, token)
        raise ValueError(f"Unknown provider: {action.provider}")

    def list_pending(self) -> list[dict[str, Any]]:
        """List all pending write-back actions."""
        return [a.to_dict() for a in WriteBackStore.list_pending()]

    def list_all(self) -> list[dict[str, Any]]:
        """List all write-back actions (all statuses)."""
        return [a.to_dict() for a in WriteBackStore.list_all()]
