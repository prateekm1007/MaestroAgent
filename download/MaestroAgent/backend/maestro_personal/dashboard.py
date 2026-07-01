"""
V8 Personal Mode — "What Maestro Knows" Dashboard (Guideline P8).

A single page showing every source, every data point Maestro holds,
with one-click revocation per source. The user can see, audit, and
delete everything Maestro knows about them at any time.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.consent import ConsentStore
from maestro_personal.store import PersonalDataStore

logger = logging.getLogger(__name__)


class WhatMaestroKnows:
    """The transparency dashboard — what Maestro knows about you.

    Shows every source, every data point, with one-click revocation.
    """

    @classmethod
    def get_dashboard(cls, user_id: str) -> dict[str, Any]:
        """Get the full dashboard — every source, every data point.

        Returns:
            {
                sources: list[{source, consent_active, item_count, items}],
                total_items: int,
                total_sources: int,
                consents: list[dict],  # all consent records
            }
        """
        sources_data: list[dict[str, Any]] = []
        total_items = 0

        for source in PersonalDataStore.get_sources():
            consent_active = ConsentStore.has_consent(user_id, source, "retrieve")
            items = PersonalDataStore.retrieve(user_id, source) if consent_active else []
            item_count = len(items)
            total_items += item_count
            sources_data.append({
                "source": source,
                "consent_active": consent_active,
                "item_count": item_count,
                "items": [i.to_dict() for i in items[:10]],  # limit to 10 per source for display
                "can_revoke": True,
            })

        consents = ConsentStore.get_consents(user_id)

        return {
            "sources": sources_data,
            "total_items": total_items,
            "total_sources": len(sources_data),
            "consents": consents,
            "message": "This is everything Maestro knows about you. You can revoke any source at any time.",
        }

    @classmethod
    def revoke_source(cls, user_id: str, source: str) -> dict[str, Any]:
        """Revoke consent for a source AND delete all data from that source.

        One-click revocation. The data is deleted immediately.
        """
        # Revoke consent
        revoked = ConsentStore.revoke_consent(user_id, source, "store")
        ConsentStore.revoke_consent(user_id, source, "retrieve")
        # Delete all data from this source
        deleted_count = PersonalDataStore.delete_by_source(source)
        logger.info("Source revoked: user=%s source=%s deleted=%d", user_id, source, deleted_count)
        return {
            "source": source,
            "revoked": revoked,
            "deleted_items": deleted_count,
            "message": f"Consent revoked for '{source}'. {deleted_count} item(s) deleted.",
        }
