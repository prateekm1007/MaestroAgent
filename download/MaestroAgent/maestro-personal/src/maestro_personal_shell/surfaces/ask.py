"""
Ask surface — thin wrapper over Core's SituationAwareAskBridge.

Calls SituationAwareAskBridge.ask() with the personal OEM state.
Does NOT reimplement question-answering. Does NOT add enterprise
entity detection. Just calls Core with personal context.
"""

from __future__ import annotations

from typing import Any


class AskSurface:
    """The Ask surface — "what did I promise Alex?"

    Calls Core's SituationAwareAskBridge.ask() directly. No HTTP.
    No enterprise oem_state. The bridge is constructed with the
    personal OEM state.
    """

    def __init__(self, shell: Any = None) -> None:
        self._shell = shell
        self._bridge = None  # lazy-init

    @property
    def bridge(self) -> Any:
        """Lazy-init the SituationAwareAskBridge with personal OEM state."""
        if self._bridge is None:
            from maestro_cognitive_council.ask_bridge import SituationAwareAskBridge
            self._bridge = SituationAwareAskBridge(oem_state=self._shell.oem_state)
        return self._bridge

    def ask(self, query: str, org_id: str = "personal") -> Any:
        """Answer a question using Situation-aware intelligence.

        Calls Core's SituationAwareAskBridge.ask() directly. The bridge:
          1. Detects which entity the question is about
          2. Finds the relevant LivingSituation
          3. Reconstructs the chronology
          4. Distinguishes facts by epistemic state
          5. Surfaces unknowns
          6. Preserves disagreements
          7. Produces a Situation-centric answer
        """
        return self.bridge.ask(query=query, org_id=org_id)
