"""
V8 Personal Mode — Local-First Config (Guideline P5).

Personal data is processed locally where possible. The architecture
supports a fully-local mode — no cloud calls for personal data. Cloud
is opt-in per computation, not per source. The user can run Maestro
Personal Mode entirely on their own machine.

A LOCAL_ONLY=true environment variable disables all cloud calls.
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


class LocalFirstConfig:
    """Manages local-first processing configuration.

    When LOCAL_ONLY=true (env var or explicit setting), all cloud
    calls are disabled. Personal data processing works entirely
    locally. Cloud calls require explicit per-computation consent.
    """

    _local_only: bool | None = None
    _cloud_consent: dict[str, bool] = {}  # computation_id → consent

    @classmethod
    def is_local_only(cls) -> bool:
        """Check if LOCAL_ONLY mode is active."""
        if cls._local_only is not None:
            return cls._local_only
        return os.environ.get("LOCAL_ONLY", "false").lower() in ("true", "1", "yes")

    @classmethod
    def set_local_only(cls, enabled: bool) -> None:
        """Explicitly set LOCAL_ONLY mode (overrides env var)."""
        cls._local_only = enabled
        logger.info("LOCAL_ONLY mode: %s", enabled)

    @classmethod
    def require_cloud_consent(cls, computation_id: str) -> None:
        """Require consent for a specific cloud computation.

        Raises RuntimeError if LOCAL_ONLY is active or consent was not granted.
        """
        if cls.is_local_only():
            raise RuntimeError(
                f"Cloud computation '{computation_id}' is blocked: LOCAL_ONLY mode is active. "
                f"Disable LOCAL_ONLY or process locally."
            )
        if not cls._cloud_consent.get(computation_id, False):
            raise RuntimeError(
                f"Cloud computation '{computation_id}' requires explicit per-computation consent. "
                f"Grant via LocalFirstConfig.grant_cloud_consent() first."
            )

    @classmethod
    def grant_cloud_consent(cls, computation_id: str) -> None:
        """Grant consent for a specific cloud computation."""
        cls._cloud_consent[computation_id] = True
        logger.info("Cloud consent granted: %s", computation_id)

    @classmethod
    def revoke_cloud_consent(cls, computation_id: str) -> None:
        """Revoke consent for a specific cloud computation."""
        cls._cloud_consent[computation_id] = False
        logger.info("Cloud consent revoked: %s", computation_id)

    @classmethod
    def has_cloud_consent(cls, computation_id: str) -> bool:
        """Check if cloud consent is granted for a computation."""
        return cls._cloud_consent.get(computation_id, False)

    @classmethod
    def clear(cls) -> None:
        """Clear all settings (for testing)."""
        cls._local_only = None
        cls._cloud_consent = {}
