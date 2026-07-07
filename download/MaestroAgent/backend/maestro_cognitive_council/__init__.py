"""
Maestro Cognitive Council — the situation-centric intelligence architecture.

This package implements the architectural reframe from the CEO directive:
Maestro is not "17 agents + dashboard." It is a Living Intelligence Layer
for Organizations, where specialists contribute perspectives to SITUATIONS,
not insights to a feed.

Four phases:
  1. Situation Engine — LivingSituation as the durable product unit
  2. Perspective Contract — structured specialist contributions
  3. Judgment Synthesizer — compare, preserve disagreement, find unknowns
  4. Delivery Governor — deterministic routing (silent/ask/briefing/whisper/prepare/urgent)

Reference: docs/MAESTRO_COGNITIVE_COUNCIL_EXECUTION_POLICY.md
"""

from .situation_engine import (
    LivingSituation,
    SituationEngine,
    SituationState,
    SideState,
    EpistemicState,
    DeliveryRoute,
    LearningState,
    EvidenceState,
    TimelineEvent,
    KnownFact,
    Unknown,
    Disagreement,
    Judgment,
    DecisionBoundary,
    StateTransition,
    SituationDelta,
    SPECIALIST_DOMAIN_MAP,
)
from .perspective import Perspective
from .judgment_synthesizer import JudgmentSynthesizer
from .delivery_governor import DeliveryGovernor, UserContext
from .consequence_path_router import ConsequencePathRouter, ConsequencePath, RoutingResult

__all__ = [
    # Phase 1: Situation Engine
    "LivingSituation",
    "SituationEngine",
    "SituationState",
    "SideState",
    "EpistemicState",
    "DeliveryRoute",
    "LearningState",
    "EvidenceState",
    "TimelineEvent",
    "KnownFact",
    "Unknown",
    "Disagreement",
    "Judgment",
    "DecisionBoundary",
    "StateTransition",
    "SituationDelta",
    "SPECIALIST_DOMAIN_MAP",
    # Phase 2: Perspective Contract
    "Perspective",
    # Phase 3: Judgment Synthesizer
    "JudgmentSynthesizer",
    # Phase 4: Delivery Governor
    "DeliveryGovernor",
    "UserContext",
    # Gate 2: Consequence-Path Router
    "ConsequencePathRouter",
    "ConsequencePath",
    "RoutingResult",
]
