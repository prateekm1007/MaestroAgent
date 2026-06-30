"""
SCIM 2.0 user provisioning endpoint.

Implements RFC 7643/7644 for automated user provisioning from enterprise IdPs
(Azure AD, Okta, Google Workspace). Supports:
  - POST /scim/v2/Users         (create)
  - GET /scim/v2/Users/{id}     (read)
  - PATCH /scim/v2/Users/{id}   (update)
  - PUT /scim/v2/Users/{id}     (replace)
  - DELETE /scim/v2/Users/{id}  (deactivate)
  - GET /scim/v2/Users          (list/filter)

Authentication: Bearer token via MAESTRO_SCIM_TOKEN env var.

JIT-provisions local users with default 'viewer' role. Existing users are
updated. Deactivated users are marked inactive (not deleted).
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any
from urllib.parse import parse_qs, urlparse

from maestro_auth.models import AuthStore

logger = logging.getLogger(__name__)


class SCIMManager:
    """SCIM 2.0 user/group provisioning manager."""

    def __init__(self, store: AuthStore) -> None:
        self.store = store

    @staticmethod
    def is_enabled() -> bool:
        return bool(os.environ.get("MAESTRO_SCIM_TOKEN"))

    @staticmethod
    def verify_token(token: str) -> bool:
        expected = os.environ.get("MAESTRO_SCIM_TOKEN", "")
        if not expected:
            return False
        return secrets.compare_digest(token, expected)

    # ─── User operations ───

    def create_user(self, scim_user: dict[str, Any]) -> dict[str, Any]:
        """Create a user from a SCIM User resource."""
        emails = scim_user.get("emails", [])
        email = next((e["value"] for e in emails if e.get("primary")), emails[0]["value"] if emails else "")
        if not email:
            raise SCIMError("No email in SCIM user resource")

        display_name = scim_user.get("displayName", "")
        external_id = scim_user.get("externalId", "")
        active = scim_user.get("active", True)

        # Check for existing user by email
        existing = self.store.get_user_by_email(email)
        if existing:
            # Update
            self.store.update_user(
                existing["id"],
                display_name=display_name,
                is_active=1 if active else 0,
                scim_external_id=external_id,
            )
            user = existing
        else:
            # Create (no password — SSO-only)
            user = self.store.create_user(
                email=email,
                display_name=display_name,
                is_admin=False,
                scim_external_id=external_id,
            )
            # Assign default 'viewer' role
            self.store.assign_role(user["id"], "viewer")

        # Save SCIM mapping
        scim_id = scim_user.get("id") or user["id"]
        self.store.save_scim_mapping(scim_id, user["id"], "User")

        # Audit
        self.store.audit(
            event_type="scim_provision",
            user_id=user["id"],
            email=email,
            resource=f"scim:user:{scim_id}",
            detail={"action": "create", "display_name": display_name, "active": active},
            success=True,
        )

        return self._user_to_scim(user["id"], scim_id)

    def get_user(self, scim_id: str) -> dict[str, Any]:
        mapping = self.store.get_scim_mapping(scim_id)
        if not mapping:
            raise SCIMNotFoundError(f"SCIM user {scim_id} not found")
        user = self.store.get_user(mapping["maestro_id"])
        if not user:
            raise SCIMNotFoundError(f"User for SCIM {scim_id} not found")
        return self._user_to_scim(user["id"], scim_id)

    def update_user(self, scim_id: str, scim_user: dict[str, Any]) -> dict[str, Any]:
        """Replace a user (PUT)."""
        mapping = self.store.get_scim_mapping(scim_id)
        if not mapping:
            raise SCIMNotFoundError(f"SCIM user {scim_id} not found")

        user = self.store.get_user(mapping["maestro_id"])
        if not user:
            raise SCIMNotFoundError(f"User for SCIM {scim_id} not found")

        emails = scim_user.get("emails", [])
        email = next((e["value"] for e in emails if e.get("primary")), emails[0]["value"] if emails else user["email"])
        display_name = scim_user.get("displayName", user["display_name"])
        active = scim_user.get("active", True)

        self.store.update_user(
            user["id"],
            email=email,
            display_name=display_name,
            is_active=1 if active else 0,
        )

        self.store.audit(
            event_type="scim_provision",
            user_id=user["id"],
            email=email,
            resource=f"scim:user:{scim_id}",
            detail={"action": "put", "display_name": display_name, "active": active},
            success=True,
        )

        return self._user_to_scim(user["id"], scim_id)

    def patch_user(self, scim_id: str, patch_op: dict[str, Any]) -> dict[str, Any]:
        """Apply a PATCH operation (RFC 7644 Section 3.5.2)."""
        mapping = self.store.get_scim_mapping(scim_id)
        if not mapping:
            raise SCIMNotFoundError(f"SCIM user {scim_id} not found")
        user = self.store.get_user(mapping["maestro_id"])
        if not user:
            raise SCIMNotFoundError(f"User for SCIM {scim_id} not found")

        operations = patch_op.get("Operations", patch_op.get("operations", []))
        if isinstance(operations, dict):
            operations = [operations]

        for op in operations:
            op_type = op.get("op", "").lower()
            path = op.get("path", "")
            value = op.get("value")

            if op_type == "replace":
                if path == "active":
                    self.store.update_user(user["id"], is_active=1 if value else 0)
                elif path == "displayName" or path == "name.familyName":
                    self.store.update_user(user["id"], display_name=value if isinstance(value, str) else value.get("familyName", ""))
                elif path.startswith("emails["):
                    if isinstance(value, dict) and "value" in value:
                        self.store.update_user(user["id"], email=value["value"])
                elif path == "" and isinstance(value, dict):
                    # Full replace
                    if "active" in value:
                        self.store.update_user(user["id"], is_active=1 if value["active"] else 0)
                    if "displayName" in value:
                        self.store.update_user(user["id"], display_name=value["displayName"])
                    if "emails" in value:
                        emails = value["emails"]
                        if emails:
                            self.store.update_user(user["id"], email=emails[0].get("value", user["email"]))

            elif op_type == "deactivate":
                self.store.update_user(user["id"], is_active=0)

        self.store.audit(
            event_type="scim_provision",
            user_id=user["id"],
            email=user["email"],
            resource=f"scim:user:{scim_id}",
            detail={"action": "patch", "operations": operations},
            success=True,
        )

        return self._user_to_scim(user["id"], scim_id)

    def delete_user(self, scim_id: str) -> None:
        """Deactivate a user (DELETE per SCIM = deactivate, not delete)."""
        mapping = self.store.get_scim_mapping(scim_id)
        if not mapping:
            raise SCIMNotFoundError(f"SCIM user {scim_id} not found")
        user = self.store.get_user(mapping["maestro_id"])
        if not user:
            raise SCIMNotFoundError(f"User for SCIM {scim_id} not found")

        self.store.update_user(user["id"], is_active=0)
        self.store.revoke_all_user_sessions(user["id"])

        self.store.audit(
            event_type="scim_provision",
            user_id=user["id"],
            email=user["email"],
            resource=f"scim:user:{scim_id}",
            detail={"action": "delete"},
            success=True,
        )

    def list_users(self, filter_expr: str | None = None, start_index: int = 1, count: int = 100) -> dict[str, Any]:
        """List users, optionally filtered. Supports simple SCIM filters."""
        users = self.store.list_users(limit=1000)

        # Apply filter (very basic — supports `userName eq "..."` and `emails.value eq "..."`)
        if filter_expr:
            users = self._apply_filter(users, filter_expr)

        # Pagination
        total = len(users)
        users = users[start_index - 1: start_index - 1 + count]

        resources = []
        for u in users:
            # Find SCIM ID (use maestro_id if no mapping exists)
            scim_id = u["id"]
            resources.append(self._user_to_scim(u["id"], scim_id))

        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": total,
            "startIndex": start_index,
            "itemsPerPage": count,
            "Resources": resources,
        }

    # ─── Helpers ───

    def _user_to_scim(self, user_id: str, scim_id: str) -> dict[str, Any]:
        user = self.store.get_user(user_id)
        if not user:
            raise SCIMNotFoundError(f"User {user_id} not found")
        return {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "id": scim_id,
            "externalId": user.get("scim_external_id") or "",
            "userName": user["email"],
            "name": {
                "formatted": user["display_name"],
            },
            "displayName": user["display_name"],
            "emails": [{"value": user["email"], "type": "work", "primary": True}],
            "active": bool(user["is_active"]),
            "meta": {
                "resourceType": "User",
                "created": user["created_at"],
                "lastModified": user["updated_at"],
                "location": f"/scim/v2/Users/{scim_id}",
            },
        }

    @staticmethod
    def _apply_filter(users: list[dict[str, Any]], filter_expr: str) -> list[dict[str, Any]]:
        """Apply a simple SCIM filter. Supports `attr eq "value"`."""
        # Parse "userName eq \"alice@acme.com\""
        import re
        match = re.match(r'(\w+(?:\.\w+)?)\s+eq\s+"([^"]+)"', filter_expr)
        if not match:
            return users  # Unsupported filter; return all
        attr, value = match.groups()
        attr_lower = value.lower()

        result = []
        for u in users:
            if attr in ("userName", "emails.value") and u["email"].lower() == attr_lower:
                result.append(u)
            elif attr == "displayName" and u["display_name"].lower() == attr_lower:
                result.append(u)
        return result


class SCIMError(Exception):
    """SCIM operation error."""
    pass


class SCIMNotFoundError(SCIMError):
    """SCIM resource not found."""
    pass
