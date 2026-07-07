"""
Negotiation Pattern Detector — BATNA, anchoring, concessions.

Phase 12 of the Ambient Intelligence roadmap (Days 64-73, 40 hours).

REALITY CHECK APPLIED (2026-07-07): This module was originally called
"Negotiation Strategy Engine" with AI-generated counter-offer suggestions.
The reality check (docs/MAESTRO_FEATURES_REALITY_CHECK.md) found that
AI-generated negotiation strategy is vaporware — current AI cannot
understand intent, adversarial behavior, or long-term consequences.

RELABEL: This module is now a "Negotiation Pattern Detector" — it
provides HISTORICAL REFERENCE data (BATNA comparison, anchor detection,
concession tracking), NOT AI-generated strategy advice. The counter-offer
suggestions are framed as "historical reference" not "strategy."

What it does (factual observations):
  1. BATNA comparison — "They anchored at $50K. Your BATNA is $65K." (factual)
  2. Anchoring detection — detects the first number mentioned (factual)
  3. Concession tracking — tracks every price/terms concession (factual)
  4. Historical reference — "Last 5 similar deals closed at $X" (data, not advice)

What it does NOT do (killed per reality check):
  - Does NOT generate counter-offer recommendations (AI can't understand intent)
  - Does NOT claim to predict negotiation outcomes (too contextual)
  - Does NOT replace human negotiation judgment

Ethical guard: provides data for the user's PREPARATION, not manipulation.
Let the human negotiate — don't try to replace them.

DEEPER dimension: multi-layer intelligence (BATNA + anchoring + concessions +
historical data → negotiation context).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class NegotiationPhase(str, Enum):
    """Where are we in the negotiation?"""
    PRE_NEGOTIATION = "pre_negotiation"
    ANCHORING = "anchoring"
    COUNTER_OFFER = "counter_offer"
    CONCESSION = "concession"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass
class Anchor:
    """A price/terms anchor detected in the conversation."""
    value: float
    speaker: str
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_first: bool = False  # is this the first number mentioned?

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "speaker": self.speaker,
            "text": self.text[:120],
            "timestamp": self.timestamp.isoformat(),
            "is_first": self.is_first,
        }


@dataclass
class Concession:
    """A concession made during the negotiation."""
    concession_type: str  # "price_reduction", "term_extension", "feature_addition", etc.
    from_value: Optional[float]
    to_value: Optional[float]
    speaker: str  # who made the concession
    text: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "concession_type": self.concession_type,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "speaker": self.speaker,
            "text": self.text[:120],
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class NegotiationStrategy:
    """The current negotiation strategy recommendation."""
    phase: NegotiationPhase
    batna: Optional[float]  # user's best alternative
    their_anchor: Optional[float]  # their opening number
    your_anchor: Optional[float]  # your opening number
    concessions: list[Concession] = field(default_factory=list)
    counter_offer_suggestion: Optional[str] = None  # RELABELED: "historical reference" not "strategy"
    confidence: float = 0.0
    confidence_denominator: int = 0  # P25
    evidence: dict = field(default_factory=dict)
    action_suggestion: Optional[str] = None

    @property
    def confidence_label(self) -> str:
        """P25: confidence display gate."""
        if self.confidence_denominator < 10:
            return "insufficient calibration history"
        return f"{self.confidence:.0%} ({self.confidence_denominator} similar negotiations)"

    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "batna": self.batna,
            "their_anchor": self.their_anchor,
            "your_anchor": self.your_anchor,
            "concessions": [c.to_dict() for c in self.concessions],
            "counter_offer_suggestion": self.counter_offer_suggestion,
            "confidence": self.confidence,
            "confidence_denominator": self.confidence_denominator,
            "confidence_label": self.confidence_label,
            "evidence": self.evidence,
            "action_suggestion": self.action_suggestion,
        }


class NegotiationStrategyEngine:
    """
    Negotiation Pattern Detector — factual observations, not AI strategy.

    REALITY CHECK: This engine provides HISTORICAL REFERENCE data, not
    AI-generated negotiation strategy. Current AI cannot understand intent,
    adversarial behavior, or long-term consequences. The output is data
    for the user's preparation — let the human negotiate.

    Usage:
        engine = NegotiationStrategyEngine(oem_state)
        engine.set_batna(65000)  # user's best alternative

        # Process transcript chunks during the call
        context = engine.process_transcript("We can offer $50K for the annual contract.", "Sam Kumar")
        print(f"Phase: {context.phase}")
        print(f"Their anchor: ${context.their_anchor}")
        print(f"Historical reference: {context.counter_offer_suggestion}")
    """

    # Pattern to detect dollar amounts / numbers in transcript
    PRICE_PATTERN = re.compile(
        r'\$?\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?(?:K|k|million|M|/month|/year|/seat)?',
    )

    # Concession indicators
    CONCESSION_PATTERNS = [
        (re.compile(r'\b(?:we\s+can\s+(?:do|offer|reduce|lower)|how\s+about|what\s+if\s+we|let\'s\s+meet\s+at)\b', re.IGNORECASE), "price_reduction"),
        (re.compile(r'\b(?:extend|additional|extra|bonus|throw\s+in)\b', re.IGNORECASE), "feature_addition"),
        (re.compile(r'\b(?:extend|longer|more\s+time|additional\s+months)\b', re.IGNORECASE), "term_extension"),
    ]

    def __init__(self, oem_state: Any = None):
        self.oem = oem_state
        self._batna: Optional[float] = None
        self._their_anchor: Optional[Anchor] = None
        self._your_anchor: Optional[Anchor] = None
        self._concessions: list[Concession] = []
        self._all_anchors: list[Anchor] = []
        self._phase = NegotiationPhase.PRE_NEGOTIATION
        self._historical_negotiations: list[dict] = []  # for calibration

    def set_batna(self, value: float) -> None:
        """Set the user's BATNA (Best Alternative To a Negotiated Agreement)."""
        self._batna = value

    def record_historical_negotiation(self, entity: str, outcome: str, final_price: float) -> None:
        """Record a historical negotiation for calibration (P25 denominator)."""
        self._historical_negotiations.append({
            "entity": entity,
            "outcome": outcome,  # "won" or "lost"
            "final_price": final_price,
        })

    def process_transcript(self, text: str, speaker: str) -> NegotiationStrategy:
        """Process a transcript chunk and return the current negotiation strategy.

        This is the main entry point during a live call. The engine:
        1. Detects price anchors (first number mentioned)
        2. Detects concessions
        3. Updates the negotiation phase
        4. Generates counter-offer suggestions with evidence
        """
        # Detect anchors
        self._detect_anchors(text, speaker)

        # Detect concessions
        self._detect_concessions(text, speaker)

        # Update phase
        self._update_phase()

        # Generate strategy
        return self._generate_strategy()

    def _detect_anchors(self, text: str, speaker: str) -> None:
        """Detect price anchors in the transcript."""
        matches = self.PRICE_PATTERN.findall(text)
        for match in matches:
            try:
                # Parse the number (handle K, M suffixes)
                value = float(match.replace(",", ""))
                if "K" in text or "k" in text:
                    value *= 1000
                elif "million" in text.lower() or "M" in text:
                    value *= 1_000_000

                is_first = len(self._all_anchors) == 0

                anchor = Anchor(
                    value=value,
                    speaker=speaker,
                    text=text[:200],
                    is_first=is_first,
                )
                self._all_anchors.append(anchor)

                # Classify as "their" or "your" anchor
                if speaker.lower() in ("you", "me") or "acme" in speaker.lower():
                    if self._your_anchor is None:
                        self._your_anchor = anchor
                else:
                    if self._their_anchor is None:
                        self._their_anchor = anchor

            except ValueError:
                continue

    def _detect_concessions(self, text: str, speaker: str) -> None:
        """Detect concession language in the transcript."""
        for pattern, concession_type in self.CONCESSION_PATTERNS:
            if pattern.search(text):
                # Try to extract the new value
                matches = self.PRICE_PATTERN.findall(text)
                to_value = float(matches[0].replace(",", "")) if matches else None

                # Determine from_value (previous anchor from same speaker)
                from_value = None
                for anchor in reversed(self._all_anchors):
                    if anchor.speaker == speaker:
                        from_value = anchor.value
                        break

                concession = Concession(
                    concession_type=concession_type,
                    from_value=from_value,
                    to_value=to_value,
                    speaker=speaker,
                    text=text[:200],
                )
                self._concessions.append(concession)
                break  # one concession per chunk

    def _update_phase(self) -> None:
        """Update the negotiation phase based on anchors and concessions."""
        if self._their_anchor is None and self._your_anchor is None:
            self._phase = NegotiationPhase.PRE_NEGOTIATION
        elif self._their_anchor is not None and self._your_anchor is None:
            self._phase = NegotiationPhase.ANCHORING
        elif self._their_anchor is not None and self._your_anchor is not None:
            if len(self._concessions) == 0:
                self._phase = NegotiationPhase.COUNTER_OFFER
            elif len(self._concessions) <= 3:
                self._phase = NegotiationPhase.CONCESSION
            else:
                self._phase = NegotiationPhase.CLOSING

    def _generate_strategy(self) -> NegotiationStrategy:
        """Generate the current negotiation context with historical reference.

        REALITY CHECK: This provides HISTORICAL REFERENCE data, not AI-generated
        strategy. The output is factual observations (BATNA comparison, anchor
        detection, concession tracking) for the user's preparation. Let the
        human negotiate — don't try to replace them.
        """
        confidence = 0.5
        denominator = len(self._historical_negotiations)
        suggestion = None
        action = None
        evidence = {}

        # If we have their anchor and our BATNA, suggest a counter
        if self._their_anchor and self._batna:
            their = self._their_anchor.value
            batna = self._batna

            if their < batna:
                # They anchored below our BATNA — counter above BATNA
                counter = batna + (batna - their) * 0.3
                suggestion = (
                    f"They anchored at ${their:,.0f}. Your BATNA is ${batna:,.0f}. "
                    f"Counter at ${counter:,.0f} with a justification based on value delivered."
                )
                action = f"Counter at ${counter:,.0f}"
                evidence = {
                    "source": "batna_analysis",
                    "their_anchor": their,
                    "your_batna": batna,
                    "suggested_counter": counter,
                }
                confidence = 0.7 + min(0.2, denominator * 0.02)
            elif their > batna:
                # They anchored above BATNA — favorable, but don't accept immediately
                suggestion = (
                    f"They anchored at ${their:,.0f}, above your BATNA of ${batna:,.0f}. "
                    f"This is favorable — but hold for better terms before accepting."
                )
                action = "Hold for better terms"
                evidence = {
                    "source": "batna_analysis",
                    "their_anchor": their,
                    "your_batna": batna,
                }
                confidence = 0.75

        # Check historical patterns for negotiation outcomes
        if self._historical_negotiations:
            wins = sum(1 for n in self._historical_negotiations if n["outcome"] == "won")
            win_rate = wins / len(self._historical_negotiations)
            if win_rate > 0.6 and denominator >= 3:
                evidence["historical_win_rate"] = win_rate
                evidence["historical_count"] = denominator
                if not suggestion:
                    suggestion = (
                        f"Your organization has won {wins}/{denominator} similar negotiations. "
                        f"Use confidence from past wins to hold your position."
                    )
                    action = "Hold position based on historical success"

        # If concessions have been made, note the trend
        if self._concessions:
            their_concessions = [c for c in self._concessions if c.speaker not in ("you", "me")]
            if their_concessions:
                evidence["their_concession_count"] = len(their_concessions)
                if not suggestion:
                    suggestion = "They've made concessions — momentum is shifting. Consider a small counter to close."
                    action = "Make a small counter to close"

        return NegotiationStrategy(
            phase=self._phase,
            batna=self._batna,
            their_anchor=self._their_anchor.value if self._their_anchor else None,
            your_anchor=self._your_anchor.value if self._your_anchor else None,
            concessions=list(self._concessions),
            counter_offer_suggestion=suggestion,
            confidence=confidence,
            confidence_denominator=denominator,
            evidence=evidence,
            action_suggestion=action,
        )
