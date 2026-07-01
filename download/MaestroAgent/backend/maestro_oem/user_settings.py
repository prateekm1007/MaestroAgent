"""
V8 P1-2 Fix — User Settings for Auto-Execute Opt-In.

The Round-35 audit identified a gap: the auto_execute_writeback endpoint
docstring promised a per-user, per-action-type opt-in setting, but the
code only checked eligibility (trust_score >= 10, 0 rollbacks). This
module adds the missing opt-in layer.

Auto-execute now requires BOTH:
  1. Eligibility: trust_score >= 10 AND rolled_back == 0 (TrustLedger)
  2. Explicit opt-in: the customer must enable auto-execute per action
     type via POST /settings/auto-execute

Default: all auto-execute disabled (empty dict). The customer must
explicitly enable each (provider, action_type) pair.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UserSettings:
    """Per-user settings for auto-execute and other governed features.

    Settings are stored in memory (per-user, keyed by user_id). In
    production, these persist to the database. The key format for
    auto-execute settings is "{provider}:{action_type}".
    """

    _auto_execute_enabled: dict[str, dict[str, bool]] = {}

    @classmethod
    def is_auto_execute_enabled(
        cls, user_id: str, provider: str, action_type: str,
    ) -> bool:
        """Check if auto-execute is explicitly enabled for this user+action.

        Returns True ONLY if the customer has explicitly called
        POST /settings/auto-execute with enabled=True for this
        (provider, action_type) pair. Default: False (disabled).
        """
        key = f"{provider}:{action_type}"
        user_settings = cls._auto_execute_enabled.get(user_id, {})
        return user_settings.get(key, False)

    @classmethod
    def set_auto_execute(
        cls, user_id: str, provider: str, action_type: str, enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable auto-execute for a (user, provider, action_type) pair.

        The customer must call this explicitly to enable auto-execute.
        Even after enabling, the eligibility check (trust_score >= 10,
        0 rollbacks) must still pass.
        """
        if user_id not in cls._auto_execute_enabled:
            cls._auto_execute_enabled[user_id] = {}
        key = f"{provider}:{action_type}"
        cls._auto_execute_enabled[user_id][key] = enabled
        logger.info(
            "Auto-execute setting: user=%s %s=%s",
            user_id, key, enabled,
        )
        return cls.get_auto_execute_settings(user_id)

    @classmethod
    def get_auto_execute_settings(cls, user_id: str) -> dict[str, Any]:
        """Get all auto-execute settings for a user."""
        user_settings = cls._auto_execute_enabled.get(user_id, {})
        return {
            "user": user_id,
            "auto_execute_enabled": dict(user_settings),
            "settings_count": len(user_settings),
        }

    @classmethod
    def get_auto_execute_with_eligibility(
        cls, user_id: str,
    ) -> list[dict[str, Any]]:
        """Get auto-execute settings with eligibility info per action type.

        For each enabled action type, also shows the trust score and
        whether the user is eligible. This lets the UI show:
        "Enabled but not yet eligible (trust_score: 3/10)" or
        "Enabled and eligible — auto-execute is active."
        """
        from maestro_oem.trust_ledger import TrustLedger
        user_settings = cls._auto_execute_enabled.get(user_id, {})
        result: list[dict[str, Any]] = []
        for key, enabled in user_settings.items():
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            provider, action_type = parts
            trust_score = TrustLedger.compute_trust_score(user_id, provider, action_type)
            eligible = TrustLedger.is_auto_execute_eligible(user_id, provider, action_type)
            result.append({
                "provider": provider,
                "action_type": action_type,
                "enabled": enabled,
                "trust_score": trust_score,
                "eligible": eligible,
                "active": enabled and eligible,
                "threshold": 10,
            })
        return result

    @classmethod
    def clear(cls) -> None:
        """Clear all settings (for testing)."""
        cls._auto_execute_enabled = {}
