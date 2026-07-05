"""
V8 Personal Mode — Phase 3-2: Ambient Personal Context.

Shows the user's OWN memory of a consented contact when they receive
a message. No third-party profile scraping. The card shows what the
USER has noted about the contact, not what the contact has posted.

WITHDRAWAL PATH (Guideline P9):
The user could keep notes about contacts in a notebook. The ambient
context adds speed; without it, the user searches their own notes
manually, which is slower but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.relationship_vault import RelationshipVault
from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.consent import ConsentStore

logger = logging.getLogger(__name__)


class AmbientContext:
    """Shows the user's own memory of a contact when they receive a message.

    The card shows:
    - The user's own notes about the contact (from RelationshipVault)
    - The user's own KG entities related to the contact
    - Recent interactions the USER logged

    It does NOT show:
    - The contact's social media posts
    - The contact's recent activity
    - Any scraped data about the contact
    """

    @staticmethod
    def get_context(user_id: str, contact_identifier: str) -> dict[str, Any]:
        """Get the user's own memory context for a contact.

        Args:
            user_id: The user receiving the message.
            contact_identifier: Name or email of the contact.

        Returns:
            {
                contact: str,
                user_memories: list[dict],  # from RelationshipVault
                kg_entities: list[dict],  # from PersonalKG
                summary: str,
                source: str,  # always "user_entered"
                withdrawal_path: str,
            }
        """
        # Get the user's own memories about this contact
        memories = RelationshipVault.get_memories(contact_identifier)
        memory_dicts = [m.to_dict() for m in memories[:5]]

        # Get KG entities related to this contact
        kg_results = PersonalKG.search(contact_identifier)
        kg_dicts = [e.to_dict() for e in kg_results[:3] if e.entity_type == "person"]

        # Build summary
        if memories:
            summary = f"You have {len(memories)} memor{'y' if len(memories) == 1 else 'ies'} about {contact_identifier}."
            if memories[0].memory_type == "birthday":
                summary += f" Their birthday is {memories[0].date}."
        elif kg_results:
            summary = f"You have {len(kg_results)} note(s) about {contact_identifier} in your knowledge graph."
        else:
            summary = f"You don't have any notes about {contact_identifier} yet."

        return {
            "contact": contact_identifier,
            "user_memories": memory_dicts,
            "kg_entities": kg_dicts,
            "summary": summary,
            "source": "user_entered",  # ALWAYS user-entered, never scraped
            "withdrawal_path": (
                "The user could keep notes about contacts in a notebook. The ambient context "
                "adds speed; without it, the user searches their own notes manually, which is "
                "slower but fully functional."
            ),
        }
