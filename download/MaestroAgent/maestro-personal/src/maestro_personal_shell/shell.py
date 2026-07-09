"""
PersonalShell — the thin shell that calls the existing Python Core directly.

Per the revised roadmap and auditor's verified-feasible finding:
direct Python API, NOT HTTP. The shell builds a SituationEngine with
the personal OEM state and delegates to Core methods.

This is NOT a dilution. The shell adds:
  - PersonalOemState (personal signals, not enterprise demo seed)
  - PersonalSalienceConfig (personal signal types, not enterprise types)
  - 4 surface wrappers (Prepare, Commitments, Ask, What Changed)

The shell does NOT reimplement any Core capability. Every intelligence
function calls the Core module that already has it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PersonalShell:
    """The thin Personal shell over the existing Python Core.

    Usage:
        state = PersonalOemState(signals=[...])
        shell = PersonalShell(oem_state=state)
        situations = shell.detect_situations()

    The shell does NOT:
      - import the enterprise oem_state singleton
      - load the enterprise demo seed
      - reimplement Brier scoring, judgment synthesis, reasoning, etc.
      - add SAML/SCIM/RBAC
      - call HTTP routes (which are wired to enterprise oem_state)

    The shell DOES:
      - build a SituationEngine with the personal OEM state
      - delegate to Core bridges (SituationPreparationBridge, SituationAwareAskBridge)
      - apply personal salience config (personal signal types)
    """

    def __init__(self, oem_state: Any = None, salience_config: Any = None) -> None:
        """Initialize the shell.

        Args:
            oem_state: A PersonalOemState (or compatible) with .signals.
                If None, an empty PersonalOemState is created.
            salience_config: A PersonalSalienceConfig (or None for default).
        """
        from maestro_personal_shell.personal_oem_state import PersonalOemState
        from maestro_personal_shell.salience import PersonalSalienceConfig

        self._oem_state = oem_state or PersonalOemState()
        self._salience_config = salience_config or PersonalSalienceConfig()
        self._situation_engine = None  # lazy-init

    @property
    def oem_state(self) -> Any:
        return self._oem_state

    @property
    def core(self) -> Any:
        """CoreWiring — exposes all Core cognitive modules to the shell.

        Per CEO directive: "80% depth on Core." This gives every surface
        access to the full engine: judgment_synthesizer, perspectives,
        calibration_primitives, reasoning_trace, briefing_bridge,
        epistemic_barrier, whisper_bridge, copilot_bridge, and more.

        Usage:
            shell.core.judgment_synthesizer
            shell.core.calibration_primitives
            shell.core.briefing_bridge
        """
        if not hasattr(self, '_core_wiring') or self._core_wiring is None:
            from maestro_personal_shell.core_wiring import CoreWiring
            self._core_wiring = CoreWiring(shell=self)
        return self._core_wiring

    @property
    def situation_engine(self) -> Any:
        """Lazy-init the SituationEngine with personal salience config applied.

        Per auditor's verified finding: _is_high_salience_signal has
        hardcoded enterprise types. We do NOT modify Core. Instead, we
        monkey-patch the engine's _is_high_salience_signal method to
        also accept personal signal types. This is the config-parameter
        approach the auditor recommended, applied via method wrapping
        because Core doesn't yet accept a config parameter.
        """
        if self._situation_engine is None:
            from maestro_cognitive_council.situation_engine import SituationEngine

            engine = SituationEngine(oem_state=self._oem_state)

            # Wrap _is_high_salience_signal to also accept personal types.
            # Do NOT modify Core. Wrap the instance method.
            original_is_high_salience = engine._is_high_salience_signal

            def personal_is_high_salience(signal: Any) -> bool:
                # First check Core's enterprise types
                if original_is_high_salience(signal):
                    return True
                # Then check personal types from config
                sig_type_raw = getattr(signal, "type", None)
                sig_type_val = getattr(sig_type_raw, "value", str(sig_type_raw)) if sig_type_raw else ""
                sig_type = str(sig_type_val).lower()
                return sig_type in self._salience_config.high_salience_types

            engine._is_high_salience_signal = personal_is_high_salience
            self._situation_engine = engine

        return self._situation_engine

    def detect_situations(self, org_id: str = "personal") -> list[Any]:
        """Detect situations from the personal signals.

        Calls SituationEngine.detect_situations() directly. No HTTP.
        No enterprise oem_state. No demo seed.

        POST-PROCESSING: Core's NEEDS_PREPARATION transition checks for
        enterprise keywords ("availability", "expectation", "production").
        Personal signals use different triggers ("meeting", "deadline",
        "tomorrow"). This method post-processes Core's output to apply
        personal expectation-mismatch triggers — without modifying Core.
        """
        engine = self.situation_engine
        situations = engine.detect_situations(org_id=org_id)
        situations = situations or []

        # Post-process: apply personal NEEDS_PREPARATION triggers
        # This is the Day 14 salience gap fix — personal signals that
        # indicate an approaching meeting or deadline should transition
        # the situation to NEEDS_PREPARATION, the same way enterprise
        # signals with "availability" or "expectation" do.
        self._apply_personal_preparation_triggers(situations)

        return situations

    def _apply_personal_preparation_triggers(self, situations: list[Any]) -> None:
        """Apply personal expectation-mismatch triggers to situations.

        This is the Day 14 fix. Core's transition at situation_engine.py:1556
        checks for "availability"/"expectation"/"production" — enterprise
        keywords. Personal signals use "meeting", "deadline", "tomorrow",
        "approaching", "not ready". This method post-processes Core's
        output to catch personal triggers.

        Does NOT modify Core. Post-processes the situation objects in-place.
        """
        # Personal keywords that indicate an expectation mismatch
        # (the user's internal state may not match what the other party expects)
        personal_trigger_keywords = [
            "meeting",         # "meeting tomorrow" — need to prepare
            "deadline",        # "deadline approaching" — need to prepare
            "tomorrow",        # time pressure
            "approaching",     # something is coming due
            "not ready",       # explicit expectation gap
            "by friday",       # deadline reference
            "by monday",       # deadline reference
            "by tuesday",      # deadline reference
            "by wednesday",    # deadline reference
            "by thursday",     # deadline reference
            "prep",            # explicit preparation mention
            "prepare",         # explicit preparation mention
            "review",          # need to review before meeting
        ]

        try:
            from maestro_cognitive_council.situation_engine import SituationState
        except ImportError:
            return  # Core not available — skip post-processing

        for situation in situations:
            # Only transition if currently in OBSERVING or MATERIAL
            current_state = getattr(situation, "state", None)
            if hasattr(current_state, "value"):
                state_val = current_state.value
            else:
                state_val = str(current_state).split(".")[-1].lower()

            if state_val not in ("observing", "material"):
                continue

            # Check if any signal for this entity contains personal triggers
            entity = str(getattr(situation, "entity", "")).lower()
            for sig in self._oem_state.signals:
                sig_entity = str(getattr(sig, "entity", "")).lower()
                if sig_entity != entity:
                    continue

                sig_text = str(getattr(sig, "text", "")).lower()
                sig_type = str(getattr(sig, "signal_type", "") or
                              getattr(getattr(sig, "type", ""), "value", "")).lower()

                # Check for personal trigger keywords in text
                has_trigger = any(kw in sig_text for kw in personal_trigger_keywords)
                # Also check for meeting/deadline signal types
                if not has_trigger:
                    has_trigger = any(kw in sig_type for kw in ("meeting", "deadline", "approaching"))

                if has_trigger:
                    try:
                        situation.transition_to(
                            SituationState.NEEDS_PREPARATION,
                            reason="Personal expectation mismatch: meeting/deadline approaching",
                            triggering_evidence_ref=getattr(sig, "signal_id", None),
                        )
                    except Exception as e:
                        logger.debug("Personal prep transition failed: %s", e)
                    break  # Only transition once per situation

    def get_situations_for_entity(self, entity: str, org_id: str = "personal") -> list[Any]:
        """Get all situations for a given entity (e.g., 'Alex')."""
        engine = self.situation_engine
        return engine.get_situations_by_entity(entity=entity, org_id=org_id) or []

    def add_signal(self, signal: Any) -> Any:
        """Add a signal to the state and apply it to relevant situations.

        Returns the SituationDelta from Core's apply_signal, or None
        if no situation was affected.
        """
        from maestro_personal_shell.personal_oem_state import PersonalSignal

        # Accept PersonalSignal or any object with .entity/.text/.type
        self._oem_state.add_signal(signal)

        # Apply to relevant situations (Core's apply_signal)
        engine = self.situation_engine
        situations = self.detect_situations()
        deltas = []
        for situation in situations:
            if getattr(situation, "entity", "").lower() == getattr(signal, "entity", "").lower():
                try:
                    delta = engine.apply_signal(situation, signal)
                    deltas.append(delta)
                except Exception as e:
                    logger.debug("apply_signal failed for situation %s: %s",
                                 getattr(situation, "situation_id", "?"), e)
        return deltas[0] if deltas else None

    def detect_stale_commitments(self, days_threshold: int = 5) -> list[Any]:
        """Detect commitments with no follow-up signal for N days.

        This is the absence-detection mechanism the auditor identified
        as missing from Core (Day 12 "no action" checkpoint). The shell
        builds it without modifying Core.
        """
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        stale = []

        # Find all commitment signals
        commitment_signals = [
            s for s in self._oem_state.signals
            if "commitment" in getattr(s, "signal_type", "").lower()
            or "commitment" in str(getattr(s, "type", "")).lower()
        ]

        for commitment in commitment_signals:
            entity = getattr(commitment, "entity", "").lower()
            commitment_time = getattr(commitment, "timestamp", now)
            if hasattr(commitment_time, "tzinfo") and commitment_time.tzinfo is None:
                commitment_time = commitment_time.replace(tzinfo=timezone.utc)

            # Find follow-up signals for the same entity AFTER the commitment
            followups = [
                s for s in self._oem_state.signals
                if getattr(s, "entity", "").lower() == entity
                and getattr(s, "signal_id", "") != getattr(commitment, "signal_id", "")
                and getattr(s, "timestamp", now) > commitment_time
            ]

            if not followups:
                age = (now - commitment_time).days
                if age >= days_threshold:
                    stale.append({
                        "commitment": commitment,
                        "entity": entity,
                        "days_stale": age,
                        "message": f"No follow-up on commitment to {entity} for {age} days",
                    })

        return stale
