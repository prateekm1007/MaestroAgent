"""
V8 Personal Mode — Phase 3-1: Relationship Memory Vault.

User-entered or mutually consented shared memories. No scraping.
Bilateral consent required for any third-party data.

WITHDRAWAL PATH (Guideline P9):
The user could keep relationship memories in a personal journal. The
vault adds searchability and structure; without it, the user relies
on their own memory, which is less complete but fully functional.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from maestro_personal.consent import ConsentStore, ConsentError

logger = logging.getLogger(__name__)


@dataclass
class RelationshipMemory:
    """A memory about a relationship — user-entered or mutually consented."""
    memory_id: str = field(default_factory=lambda: str(uuid4()))
    person: str = ""  # name or email of the person this memory is about
    memory_type: str = ""  # "birthday", "anniversary", "gift", "conversation", "event"
    content: str = ""
    date: str = ""
    source: str = "user_entered"  # always user_entered — no scraping
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "person": self.person,
            "memory_type": self.memory_type,
            "content": self.content,
            "date": self.date,
            "source": self.source,
            "created_at": self.created_at,
        }


class RelationshipVault:
    """Stores user-entered relationship memories. No scraping.

    All memories are user-entered ("I entered Sarah's birthday"). No
    memories are scraped from Sarah's Facebook. If a memory is used to
    generate output directed at the person (a gift suggestion, a message),
    bilateral consent is required.
    """

    _memories: list[RelationshipMemory] = []

    @classmethod
    def add_memory(
        cls, user_id: str, person: str, memory_type: str, content: str, date: str = "",
    ) -> RelationshipMemory:
        """Add a user-entered relationship memory.

        All memories are user-entered. The source is always 'user_entered'.
        No scraping is performed or allowed.
        """
        memory = RelationshipMemory(
            person=person,
            memory_type=memory_type,
            content=content,
            date=date,
            source="user_entered",
        )
        cls._memories.append(memory)
        logger.info("Relationship memory added: person=%s type=%s", person, memory_type)
        return memory

    @classmethod
    def get_memories(cls, person: str = "") -> list[RelationshipMemory]:
        """Get relationship memories, optionally filtered by person."""
        if person:
            return [m for m in cls._memories if person.lower() in m.person.lower()]
        return list(cls._memories)

    @classmethod
    def generate_message_for_person(
        cls, user_id: str, person: str, occasion: str = "",
    ) -> dict[str, Any]:
        """Generate a message for a person using the user's own memories.

        REQUIRES bilateral consent (Guideline P11). If the person has not
        opted in to being analyzed by Maestro, ConsentError is raised.

        The message uses only the user's own memories — never scraped data.
        """
        # Check bilateral consent
        ConsentStore.require_third_party_consent(person, "message_generation")

        # Get the user's own memories about this person
        memories = cls.get_memories(person)
        if not memories:
            return {
                "message": f"I don't have any memories about {person} in your vault. Add some to generate a personalized message.",
                "based_on": "no_memories",
            }

        # Build a simple message from memories
        memory_texts = [m.content for m in memories[:3]]
        message = f"Thinking of you, {person}. " + " ".join(memory_texts[:2])

        return {
            "message": message,
            "based_on": f"{len(memories)} user-entered memor{'y' if len(memories) == 1 else 'ies'}",
            "memories_used": [m.to_dict() for m in memories[:3]],
            "bilateral_consent": True,
        }

    @classmethod
    def delete_memory(cls, memory_id: str) -> bool:
        for i, m in enumerate(cls._memories):
            if m.memory_id == memory_id:
                cls._memories.pop(i)
                return True
        return False

    @classmethod
    def clear(cls) -> None:
        cls._memories = []
