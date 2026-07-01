"""
V8 Personal Mode — ConsentStore (Guideline P3).

Per-source consent primitive. Records every source the user has opted
into: source name, timestamp, purpose, revocable. No personal data is
accessed without a matching consent record.

This is the Personal Mode equivalent of the enterprise Trust Layer.
Every personal data access call checks ConsentStore.has_consent()
first. Accessing data without consent raises ConsentError.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ConsentError(Exception):
    """Raised when accessing personal data without consent."""
    pass


@dataclass
class ConsentRecord:
    """A single consent record — one source the user has opted into."""
    source: str  # e.g. "calendar", "gmail", "user_notes"
    purpose: str  # e.g. "morning_briefing", "memory_replay"
    granted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    revoked_at: str | None = None
    revocable: bool = True

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "purpose": self.purpose,
            "granted_at": self.granted_at,
            "revoked_at": self.revoked_at,
            "revocable": self.revocable,
            "is_active": self.is_active,
        }


class ConsentStore:
    """Per-user consent store. No personal data is accessed without consent.

    The store is in-memory for the pilot. In production, it persists to
    the database with the same audit trail as the enterprise auth store.
    """

    _consents: dict[str, dict[str, ConsentRecord]] = {}  # user_id → (source:purpose → record)
    _third_party_consents: dict[str, dict[str, ConsentRecord]] = {}  # third_party_id → (purpose → record)

    # ─── User's own data sources ────────────────────────────────────────

    @classmethod
    def grant_consent(cls, user_id: str, source: str, purpose: str, revocable: bool = True) -> ConsentRecord:
        """Grant consent for a (user, source, purpose) triple."""
        key = f"{source}:{purpose}"
        if user_id not in cls._consents:
            cls._consents[user_id] = {}
        record = ConsentRecord(source=source, purpose=purpose, revocable=revocable)
        cls._consents[user_id][key] = record
        logger.info("Consent granted: user=%s source=%s purpose=%s", user_id, source, purpose)
        return record

    @classmethod
    def revoke_consent(cls, user_id: str, source: str, purpose: str) -> bool:
        """Revoke consent for a (user, source, purpose) triple."""
        key = f"{source}:{purpose}"
        if user_id not in cls._consents or key not in cls._consents[user_id]:
            return False
        record = cls._consents[user_id][key]
        if not record.revocable:
            return False
        record.revoked_at = datetime.now(timezone.utc).isoformat()
        logger.info("Consent revoked: user=%s source=%s purpose=%s", user_id, source, purpose)
        return True

    @classmethod
    def has_consent(cls, user_id: str, source: str, purpose: str) -> bool:
        """Check if consent is active for a (user, source, purpose) triple.

        This is the gate. Every personal data access call MUST check
        this first. Accessing data without consent raises ConsentError.
        """
        key = f"{source}:{purpose}"
        if user_id not in cls._consents or key not in cls._consents[user_id]:
            return False
        return cls._consents[user_id][key].is_active

    @classmethod
    def require_consent(cls, user_id: str, source: str, purpose: str) -> None:
        """Require consent or raise ConsentError.

        Call this at the top of any function that accesses personal data.
        """
        if not cls.has_consent(user_id, source, purpose):
            raise ConsentError(
                f"Consent required: user={user_id}, source={source}, purpose={purpose}. "
                f"Grant consent via ConsentStore.grant_consent() first."
            )

    @classmethod
    def get_consents(cls, user_id: str) -> list[dict[str, Any]]:
        """Get all consent records for a user (active and revoked)."""
        if user_id not in cls._consents:
            return []
        return [r.to_dict() for r in cls._consents[user_id].values()]

    # ─── Third-party consent (Guideline P11 — bilateral) ────────────────

    @classmethod
    def grant_third_party_consent(cls, third_party_id: str, purpose: str) -> ConsentRecord:
        """Grant consent FROM a third party for a purpose.

        This is bilateral consent (Guideline P2 + P11). The third party
        must explicitly opt in. The user's consent to analyze a third
        party is NOT sufficient.
        """
        if third_party_id not in cls._third_party_consents:
            cls._third_party_consents[third_party_id] = {}
        record = ConsentRecord(source="third_party", purpose=purpose)
        cls._third_party_consents[third_party_id][purpose] = record
        logger.info("Third-party consent granted: third_party=%s purpose=%s", third_party_id, purpose)
        return record

    @classmethod
    def has_third_party_consent(cls, third_party_id: str, purpose: str) -> bool:
        """Check if a third party has consented to a purpose."""
        if third_party_id not in cls._third_party_consents:
            return False
        if purpose not in cls._third_party_consents[third_party_id]:
            return False
        return cls._third_party_consents[third_party_id][purpose].is_active

    @classmethod
    def require_third_party_consent(cls, third_party_id: str, purpose: str) -> None:
        """Require third-party consent or raise ConsentError.

        Call this before generating any output directed at a third party.
        """
        if not cls.has_third_party_consent(third_party_id, purpose):
            raise ConsentError(
                f"Third-party consent required: third_party={third_party_id}, purpose={purpose}. "
                f"The third party must explicitly opt in. The user's consent is not sufficient."
            )

    @classmethod
    def clear(cls) -> None:
        """Clear all consents (for testing)."""
        cls._consents = {}
        cls._third_party_consents = {}
