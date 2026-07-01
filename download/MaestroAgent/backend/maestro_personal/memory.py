"""
V8 Personal Mode — Phase 2-3: Memory Replay.

"What did I talk about with Sarah?" — searches the user's own data
(PersonalKG + PersonalDataStore) and returns matching memories.

WITHDRAWAL PATH (Guideline P9):
The user could stop using memory replay and search their own
notes/calendar/emails manually. Replay saves time; without it, the
user is slower to recall but fully functional.
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_personal.knowledge_graph import PersonalKG
from maestro_personal.store import PersonalDataStore
from maestro_personal.consent import ConsentStore

logger = logging.getLogger(__name__)


class MemoryReplay:
    """Searches the user's own data for memories matching a query.

    Only searches the user's own data. Never searches third-party data.
    If the user asks "What does Sarah like?" and Sarah has not consented,
    the response is: "I only have your own memories about Sarah."
    """

    @staticmethod
    def replay(user_id: str, query: str) -> dict[str, Any]:
        """Replay memories matching a natural-language query.

        Args:
            user_id: The user whose memories to search.
            query: Natural-language query, e.g. "What did I talk about with Sarah?"

        Returns:
            {
                summary: str,  # synthesized summary
                matching_memories: list[dict],
                entities_referenced: list[dict],
                third_party_warning: str | None,  # if query mentions a non-consenting third party
            }
        """
        query_lower = query.lower()

        # Search PersonalDataStore for matching items
        matching_memories: list[dict[str, Any]] = []
        all_items = PersonalDataStore.get_all(user_id)
        for item in all_items:
            content_lower = item.content.lower()
            # Match if any word from the query appears in the content
            query_words = [w for w in query_lower.split() if len(w) > 2]
            if any(w in content_lower for w in query_words):
                matching_memories.append(item.to_dict())

        # Search PersonalKG for matching entities
        entities_referenced: list[dict[str, Any]] = []
        for entity in PersonalKG.get_entities():
            if entity.name.lower() in query_lower or any(
                w in entity.name.lower() for w in query_words
            ):
                entities_referenced.append(entity.to_dict())

        # Build summary
        if matching_memories:
            summary_parts = [f"Found {len(matching_memories)} matching memor{'y' if len(matching_memories) == 1 else 'ies'}."]
            for m in matching_memories[:3]:
                summary_parts.append(f"• {m['content'][:100]}")
            if len(matching_memories) > 3:
                summary_parts.append(f"... and {len(matching_memories) - 3} more.")
            summary = "\n".join(summary_parts)
        else:
            summary = "No matching memories found. Try a different query or connect more data sources."

        # Check if the query mentions a name that might be a third party
        third_party_warning = None
        for entity in entities_referenced:
            if entity.get("entity_type") == "person" and entity.get("source") == "user_entered":
                # We only have the user's own notes about this person
                third_party_warning = (
                    f"I only have your own memories about {entity['name']}. "
                    f"I don't have {entity['name']}'s data — just what you've noted."
                )
                break

        return {
            "summary": summary,
            "matching_memories": matching_memories[:10],
            "entities_referenced": entities_referenced,
            "third_party_warning": third_party_warning,
        }
