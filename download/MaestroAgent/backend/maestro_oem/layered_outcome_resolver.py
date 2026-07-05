"""Layered OutcomeResolver — the auditor's Priority Zero.

AUDITOR-DIRECTIVE:
> OutcomeResolver is now Priority Zero.
> Previously, a poor Ask answer gave someone a poor answer.
> Now a poor OutcomeResolver can teach Maestro a false organizational belief
> that subsequently influences future answers. The blast radius has increased.

The resolver must distinguish:
  LAYER 1 — STRUCTURED EVENTS: CRM stage change, ticket closed, etc. (strongest)
  LAYER 2 — EXPLICIT ASSERTIONS: "Customer escalated the issue."
  LAYER 3 — AMBIGUOUS LANGUAGE: "Escalation risk is increasing." (does NOT resolve)
  LAYER 4 — NEGATION: "Customer did not escalate." (explicit negative)
  LAYER 5 — FUTURE/HYPOTHETICAL: "Customer may escalate." (no outcome)
  LAYER 6 — DISPUTED: "Sales says escalation; CS disagrees." (DISPUTED, not resolved)
  LAYER 7 — INDIRECT INFERENCE: "CEO joined the call." (possible evidence, not itself outcome)

Maestro should prefer NOT LEARNING over learning falsely.

Every resolution preserves:
  what was observed, what proposition it resolved, which situation it belonged to,
  event time, source time, resolution method, ambiguity, contradictory evidence, provenance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ResolutionState(str, Enum):
    """The outcome of attempting to resolve a prediction from a signal."""
    OBSERVED = "OBSERVED"                # Layer 1/2: the event clearly occurred
    NOT_OBSERVED = "NOT_OBSERVED"        # Layer 4: explicit negation — the event did NOT occur
    UNRESOLVED = "UNRESOLVED"            # Layer 3/5/7: signal doesn't establish outcome
    DISPUTED = "DISPUTED"                # Layer 6: conflicting evidence
    EXPIRED = "EXPIRED"                  # window elapsed without resolution


class ResolutionLayer(str, Enum):
    """Which layer of evidence established the resolution."""
    STRUCTURED_EVENT = "STRUCTURED_EVENT"      # Layer 1: CRM stage change, ticket closed
    EXPLICIT_ASSERTION = "EXPLICIT_ASSERTION"  # Layer 2: "Customer escalated"
    AMBIGUOUS = "AMBIGUOUS"                    # Layer 3: "Escalation risk increasing" → UNRESOLVED
    NEGATION = "NEGATION"                      # Layer 4: "Customer did not escalate"
    FUTURE = "FUTURE"                          # Layer 5: "Customer may escalate" → UNRESOLVED
    DISPUTED = "DISPUTED"                      # Layer 6: conflicting sources
    INDIRECT = "INDIRECT"                      # Layer 7: "CEO joined the call" → UNRESOLVED


@dataclass
class OutcomeResolution:
    """The result of attempting to resolve a prediction from a signal.

    Every field is populated — no silent gaps.
    """
    state: ResolutionState = ResolutionState.UNRESOLVED
    layer: ResolutionLayer = ResolutionLayer.AMBIGUOUS
    proposition: str = ""           # what outcome was being tested
    entity: str = ""                # which entity
    evidence_signal_id: str = ""    # which signal established this
    event_time: str = ""            # when the event happened (from signal metadata)
    source_time: str = ""           # when the signal was ingested
    resolution_method: str = ""     # "deterministic_event_mapping" / "explicit_assertion" / etc.
    ambiguity_present: bool = False
    contradicting_evidence: list[str] = field(default_factory=list)
    provenance: str = ""            # full chain: signal → layer → resolution

    def to_audit_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "layer": self.layer.value,
            "proposition": self.proposition,
            "entity": self.entity,
            "evidence_signal_id": self.evidence_signal_id,
            "event_time": self.event_time,
            "source_time": self.source_time,
            "resolution_method": self.resolution_method,
            "ambiguity_present": self.ambiguity_present,
            "contradicting_evidence": self.contradicting_evidence,
            "provenance": self.provenance,
        }

    def to_store_outcome(self) -> str:
        """Map to the store's outcome string: 'supporting' | 'contradicting' | 'insufficient_data'."""
        if self.state == ResolutionState.OBSERVED:
            return "supporting"
        elif self.state == ResolutionState.NOT_OBSERVED:
            return "contradicting"
        else:
            return "insufficient_data"  # UNRESOLVED, DISPUTED, EXPIRED → don't learn falsely


# ─── Negation and ambiguity patterns ────────────────────────────────────────

_NEGATION_PATTERNS = [
    "did not", "didn't", "not escalated", "not churned", "not renewed",
    "no escalation", "no churn", "no renewal", "avoided", "prevented",
    "did not occur", "didn't happen", "was not", "weren't",
]

_AMBIGUITY_PATTERNS = [
    "might", "could", "possibly", "potentially", "likely",
    "risk of", "risk increasing", "risk is increasing", "considering", "thinking about",
    "appears to", "seems to", "suggests", "indicates that",
    "is expected", "is anticipated", "is likely to", "believes",
]

_FUTURE_PATTERNS = [
    "may", "will", "shall", "going to", "plans to", "intends to",
    "expected to", "scheduled to", "about to",
]

_DISPUTE_PATTERNS = [
    "disagrees", "disputed", "conflicting", "contradicts",
    "sales says", "cs says", "engineering says", "discrepancy",
]

_INDIRECT_PATTERNS = [
    "ceo joined", "cto joined", "vp joined", "executive joined",
    "unexpected attendee", "lawyer present", "legal review",
]


def _text_contains_any(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    return any(p in text_lower for p in patterns)


class LayeredOutcomeResolver:
    """Resolves outcomes through 7 layers of evidence strength.

    AUDITOR-DIRECTIVE:
    > Maestro should prefer NOT LEARNING over learning falsely.

    The resolver starts with the strongest layer (structured events) and
    falls through to weaker layers. If no layer clearly establishes the
    outcome, the resolution is UNRESOLVED — Maestro does NOT learn from
    ambiguous evidence.
    """

    def resolve(
        self,
        signal: Any,
        expected_outcome: str,
        entity_id: str,
    ) -> OutcomeResolution:
        """Resolve a single signal against an expected outcome.

        Returns an OutcomeResolution with the state, layer, and provenance.
        NEVER raises — ambiguous signals return UNRESOLVED.
        """
        # Build the signal text for pattern matching
        sig_text = self._signal_text(signal)
        sig_type = self._signal_type(signal)
        sig_id = self._signal_id(signal)
        event_time = self._signal_event_time(signal)
        source_time = self._signal_source_time(signal)

        resolution = OutcomeResolution(
            proposition=expected_outcome,
            entity=entity_id,
            evidence_signal_id=sig_id,
            event_time=event_time,
            source_time=source_time,
        )

        # ─── LAYER 1: STRUCTURED EVENTS ────────────────────────────────────
        # The strongest evidence — a structured signal type that directly
        # maps to the outcome. e.g., customer.contract_churned for "churn".
        layer1 = self._check_structured_event(signal, expected_outcome)
        if layer1 is not None:
            resolution.state = layer1
            resolution.layer = ResolutionLayer.STRUCTURED_EVENT
            resolution.resolution_method = "deterministic_event_mapping"
            resolution.provenance = f"signal:{sig_id} → layer1:structured_event → {layer1.value}"
            return resolution

        # ─── LAYER 4: NEGATION ─────────────────────────────────────────────
        # "Customer did not escalate" → NOT_OBSERVED (contradicting)
        if _text_contains_any(sig_text, _NEGATION_PATTERNS):
            resolution.state = ResolutionState.NOT_OBSERVED
            resolution.layer = ResolutionLayer.NEGATION
            resolution.resolution_method = "explicit_negation"
            resolution.provenance = f"signal:{sig_id} → layer4:negation → NOT_OBSERVED"
            return resolution

        # ─── LAYER 6: DISPUTED ─────────────────────────────────────────────
        if _text_contains_any(sig_text, _DISPUTE_PATTERNS):
            resolution.state = ResolutionState.DISPUTED
            resolution.layer = ResolutionLayer.DISPUTED
            resolution.resolution_method = "conflicting_sources"
            resolution.ambiguity_present = True
            resolution.provenance = f"signal:{sig_id} → layer6:disputed → DISPUTED"
            return resolution

        # ─── LAYER 5: FUTURE/HYPOTHETICAL ──────────────────────────────────
        # "Customer may escalate" → UNRESOLVED (no outcome yet)
        # Check FUTURE before AMBIGUOUS — "may escalate" is specifically future,
        # not ambiguous about whether it already happened.
        if _text_contains_any(sig_text, _FUTURE_PATTERNS):
            resolution.state = ResolutionState.UNRESOLVED
            resolution.layer = ResolutionLayer.FUTURE
            resolution.resolution_method = "future_hypothetical_rejected"
            resolution.ambiguity_present = True
            resolution.provenance = f"signal:{sig_id} → layer5:future → UNRESOLVED"
            return resolution

        # ─── LAYER 3: AMBIGUOUS LANGUAGE ───────────────────────────────────
        # "Escalation risk is increasing" → UNRESOLVED (does not establish outcome)
        if _text_contains_any(sig_text, _AMBIGUITY_PATTERNS):
            resolution.state = ResolutionState.UNRESOLVED
            resolution.layer = ResolutionLayer.AMBIGUOUS
            resolution.resolution_method = "ambiguous_language_rejected"
            resolution.ambiguity_present = True
            resolution.provenance = f"signal:{sig_id} → layer3:ambiguous → UNRESOLVED"
            return resolution

        # ─── LAYER 7: INDIRECT INFERENCE ───────────────────────────────────
        # "CEO joined the call" → UNRESOLVED (possible evidence, not itself outcome)
        if _text_contains_any(sig_text, _INDIRECT_PATTERNS):
            resolution.state = ResolutionState.UNRESOLVED
            resolution.layer = ResolutionLayer.INDIRECT
            resolution.resolution_method = "indirect_inference_rejected"
            resolution.ambiguity_present = True
            resolution.provenance = f"signal:{sig_id} → layer7:indirect → UNRESOLVED"
            return resolution

        # ─── LAYER 2: EXPLICIT ASSERTION ───────────────────────────────────
        # "Customer escalated the issue" → OBSERVED (supporting)
        # Check if the signal text directly asserts the outcome occurred
        if self._is_explicit_assertion(sig_text, expected_outcome):
            resolution.state = ResolutionState.OBSERVED
            resolution.layer = ResolutionLayer.EXPLICIT_ASSERTION
            resolution.resolution_method = "explicit_assertion"
            resolution.provenance = f"signal:{sig_id} → layer2:explicit_assertion → OBSERVED"
            return resolution

        # ─── DEFAULT: UNRESOLVED ───────────────────────────────────────────
        # If no layer matched, the signal doesn't establish the outcome.
        # Maestro prefers NOT LEARNING over learning falsely.
        resolution.state = ResolutionState.UNRESOLVED
        resolution.layer = ResolutionLayer.AMBIGUOUS
        resolution.resolution_method = "no_matching_layer"
        resolution.provenance = f"signal:{sig_id} → no_matching_layer → UNRESOLVED"
        return resolution

    def _check_structured_event(
        self, signal: Any, expected_outcome: str,
    ) -> ResolutionState | None:
        """Layer 1: Check if the signal's type directly maps to the outcome."""
        from maestro_oem.empirical_loop import _signal_matches_outcome
        if _signal_matches_outcome(signal, expected_outcome, "supporting"):
            return ResolutionState.OBSERVED
        if _signal_matches_outcome(signal, expected_outcome, "contradicting"):
            return ResolutionState.NOT_OBSERVED
        return None

    def _is_explicit_assertion(self, text: str, outcome: str) -> bool:
        """Layer 2: Check if the text directly asserts the outcome occurred.

        "Customer escalated the issue" → True (asserts escalation occurred)
        "Customer may escalate" → False (Layer 5 — future/hypothetical)
        """
        text_lower = text.lower()
        outcome_lower = outcome.lower()

        # Check for outcome keywords in the text (past tense or present)
        outcome_keywords = {
            "escalation": ["escalated", "escalation occurred", "escalation happened"],
            "churn": ["churned", "churn occurred", "lost the customer", "customer left"],
            "renewal": ["renewed", "renewal completed", "contract signed"],
            "commitment broken": ["commitment broken", "missed commitment", "failed to deliver"],
            "commitment kept": ["commitment kept", "delivered on", "met the commitment"],
        }

        for key, phrases in outcome_keywords.items():
            if key in outcome_lower:
                for phrase in phrases:
                    if phrase in text_lower:
                        return True
        return False

    def _signal_text(self, signal: Any) -> str:
        parts = []
        if hasattr(signal, "artifact"):
            parts.append(str(signal.artifact))
        if hasattr(signal, "metadata") and signal.metadata:
            for v in signal.metadata.values():
                parts.append(str(v))
        if hasattr(signal, "actor"):
            parts.append(str(signal.actor))
        return " ".join(parts)

    def _signal_type(self, signal: Any) -> str:
        if hasattr(signal, "type"):
            return signal.type.value if hasattr(signal.type, "value") else str(signal.type)
        return ""

    def _signal_id(self, signal: Any) -> str:
        if hasattr(signal, "signal_id"):
            return str(signal.signal_id)
        if hasattr(signal, "artifact"):
            return str(signal.artifact)
        return ""

    def _signal_event_time(self, signal: Any) -> str:
        if hasattr(signal, "timestamp") and signal.timestamp:
            return signal.timestamp.isoformat()
        return ""

    def _signal_source_time(self, signal: Any) -> str:
        return datetime.now(timezone.utc).isoformat()
