"""
V8 Personal Mode — Phase 2-2: Personal Knowledge Graph.

The memory substrate. Entities (person, event, interest, goal, memory)
and edges (knows, attended, likes, achieved, remembers). All entities
are user-entered or derived from the user's own consented data. No
third-party entities.

WITHDRAWAL PATH (Guideline P9):
The user could stop using the knowledge graph and keep a notebook of
important people, events, and goals. The graph makes search faster;
without it, the user relies on memory and notes, which is slower but
fully functional.
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
class KGEntity:
    """An entity in the personal knowledge graph."""
    entity_id: str = field(default_factory=lambda: str(uuid4()))
    entity_type: str = ""  # "person", "event", "interest", "goal", "memory"
    name: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    source: str = "user_entered"  # where this entity came from
    consent_source: str = ""  # the consent record that authorized ingestion
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "attributes": self.attributes,
            "source": self.source,
            "consent_source": self.consent_source,
            "created_at": self.created_at,
        }


@dataclass
class KGEdge:
    """An edge in the personal knowledge graph."""
    edge_id: str = field(default_factory=lambda: str(uuid4()))
    from_entity: str = ""
    to_entity: str = ""
    edge_type: str = ""  # "knows", "attended", "likes", "achieved", "remembers"
    attributes: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "edge_type": self.edge_type,
            "attributes": self.attributes,
            "created_at": self.created_at,
        }


class PersonalKG:
    """The personal knowledge graph.

    All entities have a source field and a consent_source field. Entities
    without a valid consent trace are rejected.
    """

    _entities: dict[str, KGEntity] = {}
    _edges: list[KGEdge] = []

    @classmethod
    def add_entity(
        cls, user_id: str, entity_type: str, name: str,
        attributes: dict[str, Any] | None = None,
        source: str = "user_entered",
    ) -> KGEntity:
        """Add an entity to the graph. Requires consent for the source."""
        # User-entered entities always have consent (the user typed them in)
        if source != "user_entered":
            ConsentStore.require_consent(user_id, source, "store")

        entity = KGEntity(
            entity_type=entity_type,
            name=name,
            attributes=attributes or {},
            source=source,
            consent_source=f"{source}:store",
        )
        cls._entities[entity.entity_id] = entity
        logger.info("KG entity added: %s (%s)", name, entity_type)
        return entity

    @classmethod
    def add_edge(cls, from_entity: str, to_entity: str, edge_type: str, attributes: dict[str, Any] | None = None) -> KGEdge:
        """Add an edge between two entities."""
        if from_entity not in cls._entities or to_entity not in cls._entities:
            raise ValueError("Both entities must exist before creating an edge.")
        edge = KGEdge(
            from_entity=from_entity,
            to_entity=to_entity,
            edge_type=edge_type,
            attributes=attributes or {},
        )
        cls._edges.append(edge)
        return edge

    @classmethod
    def get_entities(cls, entity_type: str = "") -> list[KGEntity]:
        """Get all entities, optionally filtered by type."""
        if entity_type:
            return [e for e in cls._entities.values() if e.entity_type == entity_type]
        return list(cls._entities.values())

    @classmethod
    def get_entity(cls, entity_id: str) -> KGEntity | None:
        return cls._entities.get(entity_id)

    @classmethod
    def get_edges(cls, entity_id: str = "") -> list[KGEdge]:
        """Get edges, optionally filtered by from/to entity."""
        if not entity_id:
            return list(cls._edges)
        return [e for e in cls._edges if e.from_entity == entity_id or e.to_entity == entity_id]

    @classmethod
    def search(cls, query: str) -> list[KGEntity]:
        """Search entities by name (case-insensitive substring)."""
        q = query.lower()
        return [e for e in cls._entities.values() if q in e.name.lower()]

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in cls._entities.values()],
            "edges": [e.to_dict() for e in cls._edges],
            "entity_count": len(cls._entities),
            "edge_count": len(cls._edges),
        }

    @classmethod
    def clear(cls) -> None:
        cls._entities = {}
        cls._edges = []
