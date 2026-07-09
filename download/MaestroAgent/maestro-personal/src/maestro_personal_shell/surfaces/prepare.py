"""
Prepare surface — thin wrapper over Core's SituationPreparationBridge.

Calls SituationPreparationBridge.prepare_for_situation() and
prepare_for_upcoming_meetings() with the personal OEM state.
"""

from __future__ import annotations

from typing import Any


class PrepareSurface:
    """The Prepare surface — "prepare me for my meeting with Alex."

    Calls Core's SituationPreparationBridge directly. No HTTP.
    No enterprise oem_state. The bridge is constructed with the
    personal OEM state.
    """

    def __init__(self, shell: Any = None) -> None:
        self._shell = shell
        self._bridge = None  # lazy-init

    @property
    def bridge(self) -> Any:
        """Lazy-init the SituationPreparationBridge with personal OEM state."""
        if self._bridge is None:
            from maestro_cognitive_council.preparation_bridge import SituationPreparationBridge
            self._bridge = SituationPreparationBridge(
                oem_state=self._shell.oem_state,
                situation_engine=self._shell.situation_engine,
            )
        return self._bridge

    def prepare_for_situation(self, situation_id: str) -> Any:
        """Prepare for a specific situation by ID.

        Calls Core's SituationPreparationBridge.prepare_for_situation().
        """
        return self.bridge.prepare_for_situation(situation_id)

    def prepare_for_upcoming_meetings(self) -> list[Any]:
        """Prepare for all upcoming meetings that need preparation.

        Calls Core's SituationPreparationBridge.prepare_for_upcoming_meetings().
        """
        return self.bridge.prepare_for_upcoming_meetings() or []

    def get_situations_needing_preparation(self) -> list[Any]:
        """Get all situations that need preparation.

        Routes through shell.detect_situations() (which applies personal
        NEEDS_PREPARATION triggers) and filters for NEEDS_PREPARATION state.
        This ensures personal signals trigger the preparation state, not
        just enterprise keywords.
        """
        all_situations = self._shell.detect_situations()

        # Filter for NEEDS_PREPARATION state
        needing_prep = []
        for s in all_situations:
            state = getattr(s, "state", None)
            if hasattr(state, "value"):
                state_val = state.value
            else:
                state_val = str(state).split(".")[-1].lower()

            if state_val == "needs_preparation":
                needing_prep.append(s)

        return needing_prep
