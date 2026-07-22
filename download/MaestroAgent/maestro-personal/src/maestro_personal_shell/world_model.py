"""Canonical World Model — Phase 4: Cross-Surface Coherence."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_db_path() -> str:
    import os
    return os.environ.get(
        "MAESTRO_PERSONAL_DB",
        str(Path(__file__).resolve().parent / "personal.db"),
    )


class WorldModel:
    """Canonical world-model state for a single request."""

    def __init__(self, shell: Any, user_email: str = "bootstrap"):
        self._shell = shell
        self._user_email = user_email
        # Cached canonical state (lazy-computed, per-request).
        self._commitments: list[dict] | None = None
        self._situations: list[Any] | None = None
        self._stale_commitments: list[dict] | None = None
        self._completed_entities: set[str] | None = None
        self._dismissed_signal_ids: set[str] | None = None
        self._signals_by_entity: dict[str, list] | None = None
        # Phase 4 additions.
        self._disputed_entities: set[str] | None = None
        self._corrected_signal_ids: set[str] | None = None
        self._tombstoned_signal_ids: set[str] | None = None
        self._superseded_signal_ids: set[str] | None = None
        self._ledger_entries: list[dict] | None = None
        self._entities: set[str] | None = None
        self._beliefs: list[dict] | None = None
        self._unknowns: list[dict] | None = None
        self._material_changes: list[dict] | None = None
        self._relationships: list[dict] | None = None

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------

    @property
    def shell(self) -> Any:
        return self._shell

    @property
    def user_email(self) -> str:
        return self._user_email

    @property
    def signals(self) -> list:
        return self._shell.oem_state.signals

    @property
    def db_path(self) -> str:
        return _get_db_path()

    # ------------------------------------------------------------------
    # Core canonical state (situations, commitments, stale)
    # ------------------------------------------------------------------

    @property
    def situations(self) -> list:
        """All situations — computed once, reused by all surfaces."""
        if self._situations is None:
            self._situations = self._shell.detect_situations()
        return self._situations

    @property
    def commitments(self) -> list[dict]:
        """All active commitments — computed once, reused by all surfaces.

        This includes ALL filtering: completed, dismissed, non-commitment,
        tombstoned, superseded. Every surface sees the same filtered list.
        """
        if self._commitments is not None:
            return self._commitments

        from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
        surface = CommitmentsSurface(shell=self._shell)
        commitments = surface.get_active_commitments()

        # Apply ALL filters in the canonical order.
        # 1. Filter completed (topic-specific, not entity-wide)
        from maestro_personal_shell.api import _filter_completed_commitments
        commitments = _filter_completed_commitments(commitments, self.signals)

        # 2. Filter dismissed (by signal_id)
        commitments = self._filter_dismissed(commitments)

        # 3. Filter non-commitments by classification
        from maestro_personal_shell.api import _filter_non_commitments_by_classification
        commitments = _filter_non_commitments_by_classification(commitments, self.signals)

        # 4. Phase 4: filter tombstoned + superseded (from ledger)
        commitments = self._filter_tombstoned_superseded(commitments)

        self._commitments = commitments
        return self._commitments

    def _filter_dismissed(self, commitments: list[dict]) -> list[dict]:
        """Filter dismissed commitments by signal_id."""
        dismissed_ids = self.dismissed_signal_ids
        if not dismissed_ids:
            return commitments
        return [c for c in commitments if str(c.get("signal_id", "")) not in dismissed_ids]

    def _filter_tombstoned_superseded(self, commitments: list[dict]) -> list[dict]:
        """Phase 4: filter commitments that are tombstoned or superseded in the ledger."""
        exclude = self.tombstoned_signal_ids | self.superseded_signal_ids
        if not exclude:
            return commitments
        return [c for c in commitments if str(c.get("signal_id", "")) not in exclude]

    # ------------------------------------------------------------------
    # Correction / completion / dismissal state
    # ------------------------------------------------------------------

    @property
    def dismissed_signal_ids(self) -> set[str]:
        """Set of signal_ids that have been dismissed/cancelled/completed."""
        if self._dismissed_signal_ids is not None:
            return self._dismissed_signal_ids

        dismissed = set()
        for sig in self.signals:
            metadata = self._read_metadata(sig)
            status = metadata.get("status", "")
            correction = metadata.get("correction", "")
            if status in ("dismissed", "completed", "cancelled") or correction in ("dismiss", "cancel", "complete"):
                sig_id = str(getattr(sig, "signal_id", ""))
                if sig_id:
                    dismissed.add(sig_id)

        self._dismissed_signal_ids = dismissed
        return dismissed

    @property
    def corrected_signal_ids(self) -> set[str]:
        """Phase 4: set of signal_ids that have been corrected (any correction action)."""
        if self._corrected_signal_ids is not None:
            return self._corrected_signal_ids

        corrected = set()
        for sig in self.signals:
            metadata = self._read_metadata(sig)
            if metadata.get("correction"):
                sig_id = str(getattr(sig, "signal_id", ""))
                if sig_id:
                    corrected.add(sig_id)

        self._corrected_signal_ids = corrected
        return corrected

    @property
    def tombstoned_signal_ids(self) -> set[str]:
        """Phase 4: signal_ids whose ledger entry is tombstoned."""
        if self._tombstoned_signal_ids is not None:
            return self._tombstoned_signal_ids
        self._tombstoned_signal_ids = self._ledger_signal_ids_for_state("tombstoned")
        return self._tombstoned_signal_ids

    @property
    def superseded_signal_ids(self) -> set[str]:
        """Phase 4: signal_ids whose ledger entry is superseded."""
        if self._superseded_signal_ids is not None:
            return self._superseded_signal_ids
        self._superseded_signal_ids = self._ledger_signal_ids_for_state("superseded")
        return self._superseded_signal_ids

    def _ledger_signal_ids_for_state(self, state: str) -> set[str]:
        """Read signal_ids from the ledger where state matches."""
        try:
            from maestro_personal_shell.commitment_ledger import get_ledger_entries
            entries = get_ledger_entries(self._user_email, self.db_path, state=state)
            return {str(e.get("signal_id", "")) for e in entries if e.get("signal_id")}
        except Exception as e:
            logger.debug("Ledger read for state=%s failed: %s", state, e)
            return set()

    @property
    def ledger_entries(self) -> list[dict]:
        """Phase 4: all ledger entries for this user (canonical commitment lifecycle)."""
        if self._ledger_entries is not None:
            return self._ledger_entries
        try:
            from maestro_personal_shell.commitment_ledger import get_ledger_entries
            self._ledger_entries = get_ledger_entries(self._user_email, self.db_path, limit=500)
        except Exception as e:
            logger.debug("Ledger read failed: %s", e)
            self._ledger_entries = []
        return self._ledger_entries

    @property
    def disputed_entities(self) -> set[str]:
        """Phase 4: entities with a disputed commitment (from ledger state=disputed)."""
        if self._disputed_entities is not None:
            return self._disputed_entities
        self._disputed_entities = {
            str(e.get("entity", "")) for e in self.ledger_entries
            if e.get("state") == "disputed"
        }
        return self._disputed_entities

    @property
    def stale_commitments(self) -> list[dict]:
        """Stale commitments — computed once, reused by all surfaces."""
        if self._stale_commitments is None:
            self._stale_commitments = self._shell.detect_stale_commitments(days_threshold=2)
        return self._stale_commitments

    @property
    def stale_signal_ids(self) -> set[str]:
        """Set of signal_ids that are stale."""
        ids = set()
        for s in self.stale_commitments:
            commit = s.get("commitment", None)
            if commit:
                sig_id = getattr(commit, "signal_id", "") or (
                    commit.get("signal_id", "") if isinstance(commit, dict) else ""
                )
                if sig_id:
                    ids.add(str(sig_id))
        return ids

    # ------------------------------------------------------------------
    # Entity + relationship canonical state
    # ------------------------------------------------------------------

    @property
    def entities(self) -> set[str]:
        """Phase 4: canonical set of all entities (from signals + ledger)."""
        if self._entities is not None:
            return self._entities
        sig_entities = {str(getattr(sig, "entity", "")) for sig in self.signals if getattr(sig, "entity", "")}
        ledger_entities = {str(e.get("entity", "")) for e in self.ledger_entries if e.get("entity")}
        self._entities = sig_entities | ledger_entities
        return self._entities

    @property
    def relationships(self) -> list[dict]:
        """Phase 4: canonical entity relationships (from personal graph)."""
        if self._relationships is not None:
            return self._relationships
        try:
            from maestro_personal_shell.personal_graph import PersonalGraph
            graph = PersonalGraph(user_email=self._user_email)
            self._relationships = graph.get_edges() if hasattr(graph, "get_edges") else []
        except Exception as e:
            logger.debug("Graph read failed: %s", e)
            self._relationships = []
        return self._relationships

    # ------------------------------------------------------------------
    # Derived canonical state (beliefs, unknowns, material changes)
    # ------------------------------------------------------------------

    @property
    def beliefs(self) -> list[dict]:
        """Phase 4: canonical derived beliefs."""
        if self._beliefs is not None:
            return self._beliefs

        beliefs: list[dict] = []
        # Belief: stale commitments are overdue
        for sig_id in self.stale_signal_ids:
            sig = self._find_signal(sig_id)
            if sig:
                beliefs.append({
                    "entity": str(getattr(sig, "entity", "")),
                    "belief": "overdue",
                    "evidence": str(getattr(sig, "text", "")),
                    "confidence": 0.8,
                })

        # Belief: disputed commitments are contested
        for entity in self.disputed_entities:
            beliefs.append({
                "entity": entity,
                "belief": "disputed",
                "evidence": "ledger state=disputed",
                "confidence": 0.9,
            })

        # Belief: completed commitments are done
        for entity in self.completed_entities:
            beliefs.append({
                "entity": entity,
                "belief": "completed",
                "evidence": "completion signal detected",
                "confidence": 0.85,
            })

        self._beliefs = beliefs
        return self._beliefs

    @property
    def unknowns(self) -> list[dict]:
        """Phase 4: canonical open questions / unknowns."""
        if self._unknowns is not None:
            return self._unknowns

        unknowns: list[dict] = []
        # Unknown: will stale commitments be fulfilled?
        for sig_id in self.stale_signal_ids:
            sig = self._find_signal(sig_id)
            if sig:
                entity = str(getattr(sig, "entity", ""))
                if entity not in self.completed_entities:
                    unknowns.append({
                        "entity": entity,
                        "question": f"Will {entity} fulfill the stale commitment?",
                        "why": "commitment is >2 days old without completion",
                    })

        # Unknown: will disputes be resolved?
        for entity in self.disputed_entities:
            unknowns.append({
                "entity": entity,
                "question": f"Will the {entity} dispute be resolved?",
                "why": "completion is contested",
            })

        self._unknowns = unknowns
        return self._unknowns

    @property
    def material_changes(self) -> list[dict]:
        """Phase 4: canonical material changes (recent deltas)."""
        if self._material_changes is not None:
            return self._material_changes
        try:
            from maestro_personal_shell.surfaces.what_changed import WhatChangedSurface
            surface = WhatChangedSurface(shell=self._shell)
            self._material_changes = surface.detect_material_changes()
        except Exception as e:
            logger.debug("Material changes detection failed: %s", e)
            self._material_changes = []
        return self._material_changes

    # ------------------------------------------------------------------
    # Query helpers (used by surfaces)
    # ------------------------------------------------------------------

    def get_signals_for_entity(self, entity: str) -> list:
        """Get all signals for a specific entity — cached per request."""
        if self._signals_by_entity is None:
            self._signals_by_entity = {}
            for sig in self.signals:
                sig_entity = str(getattr(sig, "entity", "")).lower()
                if sig_entity not in self._signals_by_entity:
                    self._signals_by_entity[sig_entity] = []
                self._signals_by_entity[sig_entity].append(sig)

        return self._signals_by_entity.get(entity.lower(), [])

    def get_situation_for_entity(self, entity: str) -> Any | None:
        """Get the situation for a specific entity — from the canonical list."""
        entity_lower = entity.lower()
        for s in self.situations:
            if str(getattr(s, "entity", "")).lower() == entity_lower:
                return s
        return None

    @property
    def completed_entities(self) -> set[str]:
        """Set of entities with a detected completion signal."""
        if self._completed_entities is not None:
            return self._completed_entities

        from maestro_personal_shell.api import _detect_completion
        completed_ids = _detect_completion(self.signals)
        self._completed_entities = set()
        if completed_ids:
            for sig in self.signals:
                sig_id = str(getattr(sig, "signal_id", ""))
                if sig_id in completed_ids:
                    entity = str(getattr(sig, "entity", ""))
                    if entity:
                        self._completed_entities.add(entity)
        return self._completed_entities

    def is_completed(self, entity: str, commitment_text: str = "") -> bool:
        """Check if a commitment is completed — canonical answer for all surfaces."""
        return entity in self.completed_entities

    def is_dismissed(self, signal_id: str) -> bool:
        """Check if a signal has been dismissed — canonical answer for all surfaces."""
        return str(signal_id) in self.dismissed_signal_ids

    def is_disputed(self, entity: str) -> bool:
        """Phase 4: check if an entity has a disputed commitment — canonical for all surfaces."""
        return entity in self.disputed_entities

    def is_tombstoned(self, signal_id: str) -> bool:
        """Phase 4: check if a signal's commitment is tombstoned — canonical for all surfaces."""
        return str(signal_id) in self.tombstoned_signal_ids

    def is_superseded(self, signal_id: str) -> bool:
        """Phase 4: check if a signal's commitment is superseded — canonical for all surfaces."""
        return str(signal_id) in self.superseded_signal_ids

    def get_ledger_entry(self, signal_id: str) -> dict | None:
        """Phase 4: get the ledger entry for a signal_id."""
        for entry in self.ledger_entries:
            if str(entry.get("signal_id", "")) == str(signal_id):
                return entry
        return None

    def get_commitment_state(self, signal_id: str) -> str:
        """Phase 4: get the lifecycle state of a commitment."""
        entry = self.get_ledger_entry(signal_id)
        if entry:
            return str(entry.get("state", "active"))
        return "active"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_metadata(sig: Any) -> dict:
        """Read metadata from a signal, handling str/dict/None."""
        metadata = getattr(sig, "metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                import json
                metadata = json.loads(metadata)
            except Exception:
                metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return metadata

    def _find_signal(self, signal_id: str) -> Any | None:
        """Find a signal by signal_id."""
        for sig in self.signals:
            if str(getattr(sig, "signal_id", "")) == str(signal_id):
                return sig
        return None

    # ------------------------------------------------------------------
    # Cross-surface invariant helpers
    # ------------------------------------------------------------------

    def surface_answer_for_entity(self, entity: str) -> dict:
        """What should EVERY surface say about this entity?

        This is the canonical cross-surface answer. If any surface
        contradicts this, that's a coherence violation.

        Returns:
        {
            "entity": entity,
            "state": "active" | "completed" | "dismissed" | "disputed" | "tombstoned" | "superseded" | "unknown",
            "in_commitments": bool,  # should it appear in Commitments?
            "in_the_moment": bool,   # should The Moment surface it?
            "ask_says": str,         # what Ask should say
            "prepare_warns": bool,   # should Prepare warn about it?
            "what_changed_reports": bool,  # should What Changed report it?
        }
        """
        entity_lower = entity.lower()
        sig_ids = {str(getattr(s, "signal_id", "")) for s in self.get_signals_for_entity(entity_lower)}

        # Determine canonical state.
        if any(self.is_tombstoned(sid) for sid in sig_ids):
            state = "tombstoned"
        elif any(self.is_superseded(sid) for sid in sig_ids):
            state = "superseded"
        elif entity in self.disputed_entities:
            state = "disputed"
        elif entity in self.completed_entities:
            state = "completed"
        elif any(self.is_dismissed(sid) for sid in sig_ids):
            state = "dismissed"
        elif sig_ids:
            state = "active"
        else:
            state = "unknown"

        # Cross-surface expectations per the roadmap invariants.
        in_commitments = state in ("active", "at_risk", "disputed")
        in_the_moment = state in ("active", "at_risk", "disputed")  # may surface if high consequence
        prepare_warns = state in ("disputed", "at_risk")
        what_changed_reports = state in ("completed", "disputed", "dismissed", "tombstoned", "superseded")

        ask_says = {
            "active": "active commitment with citation",
            "completed": "completed with citation",
            "dismissed": "dismissed by user",
            "disputed": "completed claim exists but recipient disputes sufficiency",
            "tombstoned": "archived (tombstoned)",
            "superseded": "superseded by a newer commitment",
            "unknown": "no commitment found",
        }.get(state, "unknown")

        return {
            "entity": entity,
            "state": state,
            "in_commitments": in_commitments,
            "in_the_moment": in_the_moment,
            "ask_says": ask_says,
            "prepare_warns": prepare_warns,
            "what_changed_reports": what_changed_reports,
        }


def build_world_model(shell: Any, user_email: str = "bootstrap") -> WorldModel:
    """Build a canonical world model for a single request."""
    return WorldModel(shell=shell, user_email=user_email)
