"""
V8 Personal Mode — Personal Data Store.

The personal data store. Separate from the OEM. Stores personal
signals, memories, and notes. All access is gated by ConsentStore.
Incognito mode diverts data to ephemeral storage.

This is NOT a maestro_oem module. It is a separate namespace with
separate trust layers, separate data models, and separate consent
primitives (Guideline P2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from maestro_personal.consent import ConsentStore, ConsentError
from maestro_personal.incognito import IncognitoManager
from maestro_personal.expiry import DataExpiry, ExpirableItem

logger = logging.getLogger(__name__)


@dataclass
class PersonalItem:
    """A single personal data item — a memory, note, or signal."""
    item_id: str
    item_type: str  # "memory", "note", "signal", "habit", "goal"
    source: str  # "user_entered", "calendar", "gmail"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mode: str = "personal"  # "personal" or "work" (never mixed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_type": self.item_type,
            "source": self.source,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "mode": self.mode,
        }


class PersonalDataStore:
    """The personal data store. Separate from the OEM.

    All access is gated by ConsentStore. Incognito mode diverts data
    to ephemeral storage. Data expiration sweeps archive old items.
    """

    _items: list[PersonalItem] = []
    _by_source: dict[str, list[PersonalItem]] = {}  # source → items

    @classmethod
    def store(
        cls, user_id: str, item_type: str, source: str, content: str,
        metadata: dict[str, Any] | None = None,
    ) -> PersonalItem:
        """Store a personal data item.

        Requires consent for (source, purpose="store"). If incognito
        mode is active, the item is NOT stored — it goes to the
        ephemeral session instead.
        """
        # Check incognito mode
        session = IncognitoManager.get_session(user_id)
        if session:
            from uuid import uuid4
            item = PersonalItem(
                item_id=str(uuid4()), item_type=item_type, source=source,
                content=content, metadata=metadata or {},
            )
            session.add_ephemeral("personal_item", item.to_dict())
            logger.info("Personal item stored in incognito (ephemeral): %s", item.item_id)
            return item

        # Check consent
        ConsentStore.require_consent(user_id, source, "store")

        from uuid import uuid4
        item = PersonalItem(
            item_id=str(uuid4()), item_type=item_type, source=source,
            content=content, metadata=metadata or {},
        )
        cls._items.append(item)
        cls._by_source.setdefault(source, []).append(item)

        # Register for expiration
        DataExpiry.register_item(item.item_id, item_type, item.timestamp)

        logger.info("Personal item stored: %s type=%s source=%s", item.item_id, item_type, source)
        return item

    @classmethod
    def retrieve(
        cls, user_id: str, source: str, item_type: str = "",
    ) -> list[PersonalItem]:
        """Retrieve personal data items.

        Requires consent for (source, purpose="retrieve").
        """
        ConsentStore.require_consent(user_id, source, "retrieve")

        items = cls._by_source.get(source, [])
        if item_type:
            items = [i for i in items if i.item_type == item_type]
        return items

    @classmethod
    def get_all(cls, user_id: str) -> list[PersonalItem]:
        """Get all personal items (requires consent for each source)."""
        result: list[PersonalItem] = []
        for source in cls._by_source:
            try:
                ConsentStore.require_consent(user_id, source, "retrieve")
                result.extend(cls._by_source[source])
            except ConsentError:
                continue  # skip sources without consent
        return result

    @classmethod
    def delete_by_source(cls, source: str) -> int:
        """Delete all items from a source (used when consent is revoked)."""
        count = len(cls._by_source.get(source, []))
        cls._items = [i for i in cls._items if i.source != source]
        cls._by_source.pop(source, None)
        logger.info("Deleted %d items from source: %s", count, source)
        return count

    @classmethod
    def get_sources(cls) -> list[str]:
        """Get all sources that have data."""
        return list(cls._by_source.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all items (for testing)."""
        cls._items = []
        cls._by_source = {}
