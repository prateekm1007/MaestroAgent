"""
PersonalOemState — a duck-typed OEM state for Personal mode.

The Core's SituationEngine reads signals via:
    signals = getattr(self.oem_state, "signals", None) or []
and accesses signal attributes via getattr:
    getattr(sig, "entity"/"text"/"type"/"signal_id"/"timestamp")

So PersonalOemState needs a .signals list, and PersonalSignal needs
.entity, .text, .type, .signal_id, .timestamp attributes. We do NOT
need the full ExecutionSignal Pydantic model — duck typing is sufficient.

This is the verified-feasible path: direct Python API, not HTTP.
The shell does NOT import the enterprise oem_state singleton.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass
class PersonalSignal:
    """A personal signal — one event from the user's personal data.

    Duck-typed to match what SituationEngine expects via getattr:
      - entity: who the signal is about (e.g., "Alex")
      - text: the signal content (e.g., "I will send the proposal by Friday")
      - type: the signal type (e.g., "commitment_made", "reported_statement")
      - signal_id: unique identifier
      - timestamp: when the signal occurred
      - metadata: optional dict (Core reads .metadata.get("text") as fallback)
    """

    entity: str = ""
    text: str = ""
    signal_type: str = "reported_statement"
    signal_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)
    source_acl: str = "public"  # Core reads this for ACL; default public
    actor: str = ""  # Core reads this for some paths
    artifact: str = ""  # ExecutionSignal requires this; empty for personal

    def __post_init__(self) -> None:
        # Ensure metadata has text fallback (Core reads metadata.get("text"))
        if self.text and "text" not in self.metadata:
            self.metadata["text"] = self.text
        # Ensure actor defaults to entity
        if not self.actor:
            self.actor = self.entity

    @property
    def type(self) -> str:
        """Return the signal type as a plain string.

        Core reads signal.type via:
            sig_type_raw = getattr(sig, "type", None)
            sig_type_val = getattr(sig_type_raw, "value", str(sig_type_raw))
        A plain string works: getattr("commitment_made", "value", "commitment_made")
        returns "commitment_made".

        Nerve agents read signal.type via:
            (getattr(s, "type", "") or "").lower()
        A plain string works: "commitment_made".lower() returns "commitment_made".

        The prior _TypeWrapper was overengineered — it had .value but not
        .lower(), causing 7 Nerve agents to crash with
        '_TypeWrapper' object has no attribute 'lower'.
        A plain string satisfies ALL callers (Core + Nerve).
        """
        return self.signal_type


@dataclass
class PersonalOemState:
    """A personal OEM state — holds personal signals and a personal model.

    Duck-typed to match what SituationEngine expects via getattr:
      - .signals: list of signal objects
      - ._initialized: bool (Core checks this in some paths)

    Does NOT load the enterprise demo seed. Does NOT import the enterprise
    oem_state singleton. This is the Personal state, isolated.
    """

    signals: list[PersonalSignal] = field(default_factory=list)
    _initialized: bool = True  # Core checks this in council.py; we're always initialized

    # Core reads .model in some paths — provide an empty default
    @property
    def model(self) -> Any:
        """Return a minimal model object. Core reads model.laws, model.learning_objects."""
        class _EmptyModel:
            laws: list = []
            learning_objects: list = []
            patterns: list = []
        return _EmptyModel()

    def add_signal(self, signal: PersonalSignal) -> None:
        """Add a signal to the state."""
        self.signals.append(signal)

    def get_signals_for_entity(self, entity: str) -> list[PersonalSignal]:
        """Get all signals for a given entity."""
        return [s for s in self.signals if s.entity.lower() == entity.lower()]
