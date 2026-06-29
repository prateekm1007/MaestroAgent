"""
maestro_oem — The real Organizational Execution Model.

This package replaces the mocked OEM with a real inference engine.

Execution flow:
    Signal → Normalizer → Receipt → LearningObject → Pattern →
    Policy → Governance → Evidence → Case → Precedent →
    ExecutionModel → DecisionEngine → UI

Every provider produces different OEM changes.
No hardcoded insights. No fake data.
"""

from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
from maestro_oem.receipt import Receipt, ReceiptChain
from maestro_oem.learning_object import LearningObject, LearningObjectType
from maestro_oem.pattern import Pattern, PatternDetector, PatternType
from maestro_oem.law import OrganizationalLaw, LawStatus
from maestro_oem.model import ExecutionModel, ModelDelta
from maestro_oem.engine import OEMEngine
from maestro_oem.decision import DecisionEngine, Recommendation
from maestro_oem.confidence import ConfidenceCalculator
from maestro_oem.evidence_graph import (
    EvidenceGraph,
    EvidenceNode,
    EvidenceEdge,
    EvidenceEdgeType,
    EvidenceNodeType,
    EvidenceChain,
)
from maestro_oem.contradiction import (
    ContradictionEngine,
    ContradictionEvent,
    ContradictionLog,
    FeedbackAction,
)
from maestro_oem.replay import (
    HistoricalReplay,
    HistoricalPrediction,
    PredictionOutcome,
    ReplayMetrics,
    ReplayResult,
)
from maestro_oem.persistence import OEMStore, PersistentOEM
from maestro_oem.dependency import DependencyGraph, DependencyManager, DependencyImpact

__all__ = [
    "ExecutionSignal",
    "SignalType",
    "SignalProvider",
    "Receipt",
    "ReceiptChain",
    "LearningObject",
    "LearningObjectType",
    "Pattern",
    "PatternDetector",
    "PatternType",
    "OrganizationalLaw",
    "LawStatus",
    "ExecutionModel",
    "ModelDelta",
    "OEMEngine",
    "DecisionEngine",
    "Recommendation",
    "ConfidenceCalculator",
    "EvidenceGraph",
    "EvidenceNode",
    "EvidenceEdge",
    "EvidenceEdgeType",
    "EvidenceNodeType",
    "EvidenceChain",
    "ContradictionEngine",
    "ContradictionEvent",
    "ContradictionLog",
    "FeedbackAction",
    "HistoricalReplay",
    "HistoricalPrediction",
    "PredictionOutcome",
    "ReplayMetrics",
    "ReplayResult",
    "OEMStore",
    "PersistentOEM",
    "DependencyGraph",
    "DependencyManager",
    "DependencyImpact",
]

__version__ = "0.1.0"
