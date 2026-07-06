"""CRITICAL-01 — Permission-aware retrieval via ACLResolver.

The external audit found: source_acl="channel:slack:C-private" is not
enforced. Ask only checks acl == "private". Channel-scoped content leaks
to unauthorized users. Reproduced: executive compensation visible to any
user. This is a Fortune 100 blocker.

This module implements deny-by-default ACL resolution:
  - "public" → allow
  - "private" → allow only actor or explicit viewers
  - "channel:slack:C123" → allow only if membership verified (cache or API)
  - "team:github:engineering" → allow only if membership verified
  - Unknown ACL → DENY (fail-closed, P6)

When membership cannot be verified (no cache, no provider client), the
signal is DENIED. This is the correct behavior for enterprise: better to
hide evidence than leak restricted content.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ACLResolver:
    """Resolve whether a user can access a signal based on source_acl.

    Deny-by-default: any ACL that is not exactly "public" requires
    explicit permission verification. If verification fails or is
    unavailable, the signal is hidden (P6: fail-closed).
    """

    def __init__(
        self,
        membership_cache: dict[str, bool] | None = None,
        provider_clients: dict[str, Any] | None = None,
    ) -> None:
        # membership_cache: {"slack:C123456:alice@acme.com": True, ...}
        self._membership_cache = membership_cache or {}
        # provider_clients: {"slack": SlackClient, "github": GitHubClient, ...}
        self._provider_clients = provider_clients or {}

    def can_access(self, signal: Any, user_email: str) -> bool:
        """Check if user_email can access the given signal.

        Args:
            signal: An ExecutionSignal with a source_acl attribute.
            user_email: The email of the user requesting access.

        Returns:
            True if the user can access the signal, False otherwise.
            Deny-by-default for any non-public ACL.
        """
        acl = getattr(signal, "source_acl", "public")

        # Public — anyone can see
        if acl == "public" or not acl:
            return True

        # Private — actor or explicit viewers only
        if acl == "private":
            return self._check_private(signal, user_email)

        # Channel-scoped — requires membership resolution
        if ":" in acl:
            return self._check_scoped_membership(acl, user_email)

        # Unknown ACL type — DENY (fail-closed)
        logger.warning(
            "Unknown ACL type %r for user %s — denying (fail-closed)", acl, user_email,
        )
        return False

    def _check_private(self, signal: Any, user_email: str) -> bool:
        """Check private ACL: actor or explicit viewers only."""
        if not user_email:
            return False  # fail-closed — no user context
        viewers = []
        if hasattr(signal, "metadata") and signal.metadata:
            viewers = signal.metadata.get("viewers", [])
        actor = getattr(signal, "actor", "")
        return actor == user_email or user_email in viewers

    def _check_scoped_membership(self, acl: str, user_email: str) -> bool:
        """Check scoped membership (channel:slack:C123, team:github:eng, etc.).

        Format: <scope_type>:<provider>:<scope_id>
        Examples:
          channel:slack:C123456
          team:github:engineering
          project:jira:PROJ
          space:confluence:ENG

        Resolution priority:
        1. Pre-synced membership cache (fast)
        2. Live provider API call (slow, if client available)
        3. If neither available — DENY (fail-closed)
        """
        parts = acl.split(":", 2)
        if len(parts) < 3:
            logger.warning("Malformed scoped ACL %r — denying", acl)
            return False

        scope_type = parts[0]   # "channel", "team", "project", "space"
        provider = parts[1]     # "slack", "github", "jira", "confluence"
        scope_id = parts[2]     # "C123456", "engineering", "PROJ", "ENG"

        # Option 1: check pre-synced membership cache
        cache_key = f"{provider}:{scope_id}:{user_email}"
        if cache_key in self._membership_cache:
            return self._membership_cache[cache_key]

        # Option 2: live API call (if provider client available)
        if provider in self._provider_clients:
            try:
                client = self._provider_clients[provider]
                is_member = client.check_membership(scope_id, user_email)
                # Cache the result
                self._membership_cache[cache_key] = is_member
                return is_member
            except Exception as e:
                logger.warning(
                    "Membership check failed for ACL %s, user %s: %s — denying",
                    acl, user_email, e,
                )
                return False  # fail-closed

        # Option 3: cannot verify — DENY (fail-closed)
        logger.info(
            "Cannot verify membership for ACL %s, user %s — denying (fail-closed). "
            "No membership cache entry and no %s provider client available.",
            acl, user_email, provider,
        )
        return False
