"""
Core wiring — exposes all Core modules to the Personal shell.

Per CEO directive: "80% depth on Core. The complexity behind the screens."
This module initializes all Core cognitive modules with the personal OEM
state, so every surface can call the full engine — not just 5 modules.

Each module is lazy-initialized (only imported when first accessed) to
avoid startup overhead and to handle modules that may not be available
in all environments.

The pattern: every module is constructed with the personal OEM state
(via duck typing, same as SituationEngine). No Core modification. No
enterprise coupling. Just wiring.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class CoreWiring:
    """Lazy-accessor for all Core cognitive modules, wired to personal state.

    Usage:
        core = CoreWiring(shell)
        judgment = core.judgment_synthesizer
        perspectives = core.perspectives
        calibration = core.calibration_primitives

    Each property lazy-imports and lazy-initializes the module on first
    access, caching the instance for reuse.
    """

    def __init__(self, shell: Any) -> None:
        self._shell = shell
        self._cache: dict[str, Any] = {}

    @property
    def oem_state(self) -> Any:
        return self._shell.oem_state

    @property
    def situation_engine(self) -> Any:
        return self._shell.situation_engine

    # ── Judgment + Decision ──────────────────────────────────────────

    @property
    def judgment_synthesizer(self) -> Any:
        """JudgmentSynthesizer — the false-decisiveness gate + decision boundary.

        Ask uses this to show: "What can be decided now, what should wait,
        what would change the recommendation."
        """
        if "judgment_synthesizer" not in self._cache:
            try:
                from maestro_cognitive_council.judgment_synthesizer import JudgmentSynthesizer
                self._cache["judgment_synthesizer"] = JudgmentSynthesizer()
            except Exception as e:
                logger.debug("JudgmentSynthesizer init failed: %s", e)
                self._cache["judgment_synthesizer"] = None
        return self._cache["judgment_synthesizer"]

    @property
    def consequence_path_router(self) -> Any:
        """ConsequencePathRouter — routes decisions by consequence paths.

        Ask uses this to show consequence paths and decision boundaries.
        """
        if "consequence_path_router" not in self._cache:
            try:
                from maestro_cognitive_council.consequence_path_router import ConsequencePathRouter
                self._cache["consequence_path_router"] = ConsequencePathRouter()
            except Exception as e:
                logger.debug("ConsequencePathRouter init failed: %s", e)
                self._cache["consequence_path_router"] = None
        return self._cache["consequence_path_router"]

    # ── Perspectives ─────────────────────────────────────────────────

    @property
    def perspectives(self) -> list[Any]:
        """Perspective instances — the specialist views on a situation.

        Ask uses this to show multiple perspectives (e.g., engineering,
        customer, legal, financial) on the same situation.
        """
        if "perspectives" not in self._cache:
            try:
                from maestro_cognitive_council.perspective import Perspective
                # Create default perspectives — these are the specialist
                # views that the council synthesizes
                self._cache["perspectives"] = Perspective.create_default_set()
            except Exception as e:
                logger.debug("Perspective init failed: %s", e)
                self._cache["perspectives"] = []
        return self._cache["perspectives"]

    # ── Calibration + Learning ───────────────────────────────────────

    @property
    def calibration_primitives(self) -> Any:
        """CalibrationPrimitives — Brier score + 10-bucket calibration.

        Commitments uses this to show: "You've kept 7/10 like this"
        and the calibration behind that number.
        """
        if "calibration_primitives" not in self._cache:
            try:
                from maestro_cognitive_council.calibration_primitives import CalibrationPrimitives
                self._cache["calibration_primitives"] = CalibrationPrimitives()
            except Exception as e:
                logger.debug("CalibrationPrimitives init failed: %s", e)
                self._cache["calibration_primitives"] = None
        return self._cache["calibration_primitives"]

    @property
    def behavioral_learning_engine(self) -> Any:
        """BehavioralLearningEngine — hypothesis → prediction → outcome → learning.

        Commitments uses this to track kept/broken history and feed
        outcomes back into the learning loop.
        """
        if "behavioral_learning_engine" not in self._cache:
            try:
                from maestro_cognitive_council.behavioral_learning_engine import BehavioralLearningEngine
                self._cache["behavioral_learning_engine"] = BehavioralLearningEngine(
                    oem_state=self.oem_state,
                )
            except Exception as e:
                logger.debug("BehavioralLearningEngine init failed: %s", e)
                self._cache["behavioral_learning_engine"] = None
        return self._cache["behavioral_learning_engine"]

    # ── Reasoning + Provenance ───────────────────────────────────────

    @property
    def reasoning_trace(self) -> Any:
        """ReasoningTrace — the provenance chain for any inference.

        Ask uses this to show: "Here's how Maestro arrived at this answer"
        — the full chain from evidence to conclusion.
        """
        if "reasoning_trace" not in self._cache:
            try:
                from maestro_cognitive_council.reasoning_trace import ReasoningTrace
                self._cache["reasoning_trace"] = ReasoningTrace()
            except Exception as e:
                logger.debug("ReasoningTrace init failed: %s", e)
                self._cache["reasoning_trace"] = None
        return self._cache["reasoning_trace"]

    # ── Briefing ─────────────────────────────────────────────────────

    @property
    def briefing_bridge(self) -> Any:
        """SituationBriefingBridge — the morning briefing engine.

        Home uses this to show an orchestrated morning briefing with
        overnight changes, the one thing to focus on, and knowledge gaps.
        """
        if "briefing_bridge" not in self._cache:
            try:
                from maestro_cognitive_council.briefing_bridge import SituationBriefingBridge
                self._cache["briefing_bridge"] = SituationBriefingBridge(
                    oem_state=self.oem_state,
                    situation_engine=self.situation_engine,
                )
            except Exception as e:
                logger.debug("BriefingBridge init failed: %s", e)
                self._cache["briefing_bridge"] = None
        return self._cache["briefing_bridge"]

    # ── Epistemic Honesty ────────────────────────────────────────────

    @property
    def epistemic_barrier(self) -> Any:
        """EpistemicBarrier — honest refusal when evidence is insufficient.

        Whisper + Ask use this to say "insufficient calibration history"
        instead of a confident wrong answer. The intellectual honesty gate.
        """
        if "epistemic_barrier" not in self._cache:
            try:
                from maestro_cognitive_council.epistemic_barrier import EpistemicBarrier
                self._cache["epistemic_barrier"] = EpistemicBarrier()
            except Exception as e:
                logger.debug("EpistemicBarrier init failed: %s", e)
                self._cache["epistemic_barrier"] = None
        return self._cache["epistemic_barrier"]

    # ── Access Control ───────────────────────────────────────────────

    @property
    def acl_barrier(self) -> Any:
        """ACLBarrier — access control for signals.

        Ensures private signals stay private. Whisper + Ask check this
        before surfacing content.
        """
        if "acl_barrier" not in self._cache:
            try:
                from maestro_cognitive_council.acl_barrier import ACLBarrier
                self._cache["acl_barrier"] = ACLBarrier()
            except Exception as e:
                logger.debug("ACLBarrier init failed: %s", e)
                self._cache["acl_barrier"] = None
        return self._cache["acl_barrier"]

    # ── Whisper Content ──────────────────────────────────────────────

    @property
    def whisper_bridge(self) -> Any:
        """WhisperSituationBridge — generates Whisper content from situations.

        Whisper uses this (alongside DeliveryGovernor) to produce the
        actual whisper text — not just "stale commitment" but the
        nuanced, situation-aware content Core's bridge generates.
        """
        if "whisper_bridge" not in self._cache:
            try:
                from maestro_cognitive_council.whisper_bridge import WhisperSituationBridge
                self._cache["whisper_bridge"] = WhisperSituationBridge(
                    oem_state=self.oem_state,
                    situation_engine=self.situation_engine,
                )
            except Exception as e:
                logger.debug("WhisperBridge init failed: %s", e)
                self._cache["whisper_bridge"] = None
        return self._cache["whisper_bridge"]

    # ── Copilot (Live Intelligence) ──────────────────────────────────

    @property
    def copilot_bridge(self) -> Any:
        """CopilotSituationBridge — live call intelligence.

        Prepare uses this to call pre_call_briefing() before a meeting.
        This is the Cluely-class depth: real-time suggestions during calls
        and post-call summaries.
        """
        if "copilot_bridge" not in self._cache:
            try:
                from maestro_cognitive_council.copilot_bridge import CopilotSituationBridge
                self._cache["copilot_bridge"] = CopilotSituationBridge(
                    oem_state=self.oem_state,
                    situation_engine=self.situation_engine,
                )
            except Exception as e:
                logger.debug("CopilotBridge init failed: %s", e)
                self._cache["copilot_bridge"] = None
        return self._cache["copilot_bridge"]

    # ── Governance + Autobiography ───────────────────────────────────

    @property
    def governance_surface(self) -> Any:
        """GovernanceSurface — governance handoff for operator actions.

        Used when a situation needs human governance (e.g., falsifying
        a pattern, overriding a decision boundary).
        """
        if "governance_surface" not in self._cache:
            try:
                from maestro_cognitive_council.governance_surface import GovernanceSurface
                self._cache["governance_surface"] = GovernanceSurface()
            except Exception as e:
                logger.debug("GovernanceSurface init failed: %s", e)
                self._cache["governance_surface"] = None
        return self._cache["governance_surface"]

    @property
    def institutional_autobiography(self) -> Any:
        """InstitutionalAutobiography — the org/personal memory narrative.

        What Changed uses this to show the longer-arc story, not just
        the latest delta. "The last three times you faced this situation..."
        """
        if "institutional_autobiography" not in self._cache:
            try:
                from maestro_cognitive_council.institutional_autobiography import InstitutionalAutobiography
                self._cache["institutional_autobiography"] = InstitutionalAutobiography(
                    oem_state=self.oem_state,
                )
            except Exception as e:
                logger.debug("InstitutionalAutobiography init failed: %s", e)
                self._cache["institutional_autobiography"] = None
        return self._cache["institutional_autobiography"]

    # ── Situation Persistence ────────────────────────────────────────

    @property
    def situation_store(self) -> Any:
        """SituationStore — persists situations across restarts.

        The shell uses this to save/load situations so they survive
        app restart. Currently situations are in-memory only.
        """
        if "situation_store" not in self._cache:
            try:
                from maestro_cognitive_council.situation_store import SituationStore
                import tempfile, os
                db_path = os.environ.get(
                    "MAESTRO_PERSONAL_DB",
                    str(tempfile.gettempdir() + "/maestro_personal_situations.db"),
                )
                # Use the same DB as signals, different table
                self._cache["situation_store"] = SituationStore(db_path=db_path)
            except Exception as e:
                logger.debug("SituationStore init failed: %s", e)
                self._cache["situation_store"] = None
        return self._cache["situation_store"]

    # ── Summary: what's wired ────────────────────────────────────────

    @property
    def wired_count(self) -> int:
        """How many Core modules are successfully wired."""
        modules = [
            self.judgment_synthesizer,
            self.consequence_path_router,
            self.perspectives,
            self.calibration_primitives,
            self.behavioral_learning_engine,
            self.reasoning_trace,
            self.briefing_bridge,
            self.epistemic_barrier,
            self.acl_barrier,
            self.whisper_bridge,
            self.copilot_bridge,
            self.governance_surface,
            self.institutional_autobiography,
            self.situation_store,
        ]
        return sum(1 for m in modules if m is not None) + 5  # +5 already wired (engine, audit_safety, ask, delivery, prep)

    @property
    def wired_modules(self) -> list[str]:
        """Names of successfully wired modules."""
        wired = ["situation_engine", "audit_safety", "ask_bridge", "delivery_governor", "preparation_bridge"]
        if self.judgment_synthesizer: wired.append("judgment_synthesizer")
        if self.consequence_path_router: wired.append("consequence_path_router")
        if self.perspectives: wired.append("perspective")
        if self.calibration_primitives: wired.append("calibration_primitives")
        if self.behavioral_learning_engine: wired.append("behavioral_learning_engine")
        if self.reasoning_trace: wired.append("reasoning_trace")
        if self.briefing_bridge: wired.append("briefing_bridge")
        if self.epistemic_barrier: wired.append("epistemic_barrier")
        if self.acl_barrier: wired.append("acl_barrier")
        if self.whisper_bridge: wired.append("whisper_bridge")
        if self.copilot_bridge: wired.append("copilot_bridge")
        if self.governance_surface: wired.append("governance_surface")
        if self.institutional_autobiography: wired.append("institutional_autobiography")
        if self.situation_store: wired.append("situation_store")
        return wired
