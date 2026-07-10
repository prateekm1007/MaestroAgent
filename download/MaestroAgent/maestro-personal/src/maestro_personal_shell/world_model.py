"""
Canonical World Model Reader — P24 fix for cross-surface coherence.

The ENTROPY_RECOVERY.md P24 principle states:
"Cross-surface coherence check — same entity through all surfaces must agree"

The auditor found ~18% contradiction rate because each surface (Commitments,
The Moment, Prepare, What Changed, Ask) independently calls build_shell()
and recomputes state from raw signals. If one surface detects completion
and another doesn't, they contradict.

This module provides a CANONICAL world-model reader. All surfaces read
from the same computed state, computed once per request. This eliminates
cross-surface contradictions by construction.

The world model is computed once per request (not cached across requests,
because the underlying signals may change). Within a single request, all
surfaces see the same state.
"""

from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WorldModel:
    """Canonical world-model state for a single request.

    All surfaces read from this object instead of independently recomputing.
    This ensures cross-surface coherence (P24).
    """

    def __init__(self, shell: Any, user_email: str = "bootstrap"):
        self._shell = shell
        self._user_email = user_email
        self._commitments: list[dict] | None = None
        self._situations: list[Any] | None = None
        self._stale_commitments: list[dict] | None = None
        self._completed_entities: set[str] | None = None
        self._dismissed_signal_ids: set[str] | None = None
        self._signals_by_entity: dict[str, list] | None = None

    @property
    def shell(self) -> Any:
        return self._shell

    @property
    def signals(self) -> list:
        return self._shell.oem_state.signals

    @property
    def situations(self) -> list:
        """All situations — computed once, reused by all surfaces."""
        if self._situations is None:
            self._situations = self._shell.detect_situations()
        return self._situations

    @property
    def commitments(self) -> list[dict]:
        """All active commitments — computed once, reused by all surfaces.

        This includes ALL filtering: completed, dismissed, non-commitment.
        Every surface sees the same filtered list.
        """
        if self._commitments is not None:
            return self._commitments

        from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
        surface = CommitmentsSurface(shell=self._shell)
        commitments = surface.get_active_commitments()

        # Apply ALL filters in the canonical order
        # 1. Filter completed (topic-specific, not entity-wide)
        from maestro_personal_shell.api import _filter_completed_commitments
        commitments = _filter_completed_commitments(commitments, self.signals)

        # 2. Filter dismissed (by signal_id)
        commitments = self._filter_dismissed(commitments)

        # 3. Filter non-commitments by classification
        from maestro_personal_shell.api import _filter_non_commitments_by_classification
        commitments = _filter_non_commitments_by_classification(commitments, self.signals)

        self._commitments = commitments
        return self._commitments

    def _filter_dismissed(self, commitments: list[dict]) -> list[dict]:
        """Filter dismissed commitments by signal_id."""
        dismissed_ids = self.dismissed_signal_ids
        if not dismissed_ids:
            return commitments
        return [c for c in commitments if str(c.get("signal_id", "")) not in dismissed_ids]

    @property
    def dismissed_signal_ids(self) -> set[str]:
        """Set of signal_ids that have been dismissed/cancelled."""
        if self._dismissed_signal_ids is not None:
            return self._dismissed_signal_ids

        dismissed = set()
        for sig in self.signals:
            metadata = getattr(sig, "metadata", {}) or {}
            if isinstance(metadata, str):
                try:
                    import json
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            status = metadata.get("status", "")
            correction = metadata.get("correction", "")
            if status in ("dismissed", "completed", "cancelled") or correction in ("dismiss", "cancel", "complete"):
                sig_id = str(getattr(sig, "signal_id", ""))
                if sig_id:
                    dismissed.add(sig_id)

        self._dismissed_signal_ids = dismissed
        return dismissed

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

    def is_completed(self, entity: str, commitment_text: str = "") -> bool:
        """Check if a commitment is completed — canonical answer for all surfaces."""
        # Check if any completion signal exists for this entity
        from maestro_personal_shell.api import _detect_completion
        completed_ids = _detect_completion(self.signals)
        if not completed_ids:
            return False

        # Check if any completed signal belongs to this entity
        for sig in self.signals:
            sig_id = str(getattr(sig, "signal_id", ""))
            if sig_id in completed_ids:
                if str(getattr(sig, "entity", "")).lower() == entity.lower():
                    return True
        return False

    def is_dismissed(self, signal_id: str) -> bool:
        """Check if a signal has been dismissed — canonical answer for all surfaces."""
        return str(signal_id) in self.dismissed_signal_ids


def build_world_model(shell: Any, user_email: str = "bootstrap") -> WorldModel:
    """Build a canonical world model for a single request.

    All surfaces should call this instead of independently recomputing state.
    This ensures cross-surface coherence (P24).
    """
    return WorldModel(shell=shell, user_email=user_email)
