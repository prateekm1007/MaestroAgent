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
    # Gate 0: 4-Dimensional State Model
    EpistemicDimensionState,
    OperationalDimensionState,
    DeliveryDimensionState,
    LearningDimensionState,
    DimensionTransition,
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
from .delivery_governor import (
    DeliveryGovernor,
    UserContext,
    OpportunityCostModel,
    OpportunityCostAssessment,
)
from .consequence_path_router import ConsequencePathRouter, ConsequencePath, RoutingResult
from .benchmark_types import BenchmarkStory, BenchmarkSignal, CheckpointExpectation
from .world_model_benchmark import ALL_STORIES, get_story, get_stories_by_failure_shape
from .behavioral_learning_engine import BehavioralLearningEngine, LearningArcResult
from .ask_bridge import SituationAwareAskBridge, AskResult
from .briefing_bridge import SituationBriefingEngine, SituationCentricBriefing
from .preparation_bridge import SituationPreparationBridge, SituationPreparation
from .whisper_bridge import WhisperSituationBridge, WhisperResult, SituationWhisper
from .copilot_bridge import CopilotSituationBridge, CopilotPreCallBriefing, CopilotPostCallSummary
from .epistemic_barrier import mark_model_output_as_shadow, is_model_output, can_be_used_as_evidence, filter_evidence_signals
from .acl_barrier import propagate_acl_restrictions, redact_restricted_content
from .situation_store import SituationStore
from .audit_safety import (
    is_falsified, filter_falsified_situations,
    check_prompt_injection, sanitize_signal_for_council,
    filter_signals_by_timestamp,
    classify_transcript_chunk, should_treat_as_commitment,
    entities_likely_renamed, find_renamed_entity,
)

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
    # Gate 0: 4-Dimensional State Model
    "EpistemicDimensionState",
    "OperationalDimensionState",
    "DeliveryDimensionState",
    "LearningDimensionState",
    "DimensionTransition",
    # Phase 2: Perspective Contract
    "Perspective",
    # Phase 3: Judgment Synthesizer
    "JudgmentSynthesizer",
    # Phase 4: Delivery Governor
    "DeliveryGovernor",
    "UserContext",
    "OpportunityCostModel",
    "OpportunityCostAssessment",
    # Gate 2: Consequence-Path Router
    "ConsequencePathRouter",
    "ConsequencePath",
    "RoutingResult",
    # Gate 0: World Model Benchmark
    "BenchmarkStory",
    "BenchmarkSignal",
    "CheckpointExpectation",
    "ALL_STORIES",
    "get_story",
    "get_stories_by_failure_shape",
    # Gate 4: Behavioral Learning
    "BehavioralLearningEngine",
    "LearningArcResult",
    # Surface Wiring: Ask → Situation Engine
    "SituationAwareAskBridge",
    "AskResult",
    # Surface Wiring: Briefing → Situation Judgment
    "SituationBriefingEngine",
    "SituationCentricBriefing",
    # Surface Wiring: Prepare → LivingSituation
    "SituationPreparationBridge",
    "SituationPreparation",
    # Surface Wiring: Whisper → Delivery Governor
    "WhisperSituationBridge",
    "WhisperResult",
    "SituationWhisper",
    # Surface Wiring: Copilot → Situation Engine
    "CopilotSituationBridge",
    "CopilotPreCallBriefing",
    "CopilotPostCallSummary",
]
