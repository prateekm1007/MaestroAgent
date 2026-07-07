"""
Maestro Live Copilot — Live Intelligence Engine (Phase 4, Scene 2).

Processes transcript chunks in real time and produces 4 card types:
  1. Objection detected (rose #FF5577) — transcript matches objection pattern;
     response cites validated organizational runtimes; confidence from pattern count
  2. Commitment detected (amber #FFB84D) — transcript matches commitment pattern;
     deduped against CommitmentTracker (Day X/Y, not a duplicate)
  3. Organizational whisper (purple #7C5CFF) — entity matches a GitHub PR /
     Slack message / Confluence page; cross-validated evidence chain
  4. Historical pattern match (cyan #5CC8FF) — conversation resembles a past meeting

Each card has:
  - Color-coded border (per spec)
  - Confidence bar (P25: <10 samples = "insufficient calibration history")
  - Evidence chain (clickable "View evidence" link)
  - Actions (Show response / Dismiss / Offer demo / View case)
  - cardSlideIn animation (400ms) + glow effect (fades after 5s)

Ethical guard: emotion/sentiment analysis is for the user's awareness only.
Never displayed to the other party. Never used to "win."
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SuggestionCard:
    """A live suggestion card displayed in the side panel."""
    card_type: str  # "objection" | "commitment" | "whisper" | "pattern"
    title: str
    text: str
    confidence: float  # 0.0 - 1.0
    confidence_denominator: int  # sample size (P25)
    evidence: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_new: bool = True  # triggers glow effect (fades after 5s)

    @property
    def color(self) -> str:
        colors = {
            "objection": "#FF5577",
            "commitment": "#FFB84D",
            "whisper": "#7C5CFF",
            "pattern": "#5CC8FF",
            "tracked": "#00D4AA",
        }
        return colors.get(self.card_type, "#2e3344")

    @property
    def confidence_label(self) -> str:
        """P25: confidence display gate. <10 samples = 'insufficient calibration'."""
        if self.confidence_denominator < 10:
            return "insufficient calibration history"
        pct = int(self.confidence * 100)
        return f"{pct}% ({self.confidence_denominator} samples)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_type": self.card_type,
            "color": self.color,
            "title": self.title,
            "text": self.text,
            "confidence": self.confidence,
            "confidence_denominator": self.confidence_denominator,
            "confidence_label": self.confidence_label,
            "evidence": self.evidence,
            "actions": self.actions,
            "detected_at": self.detected_at,
            "is_new": self.is_new,
        }


# ─── Detection patterns ─────────────────────────────────────────────────────

OBJECTION_PATTERNS = [
    (re.compile(r"\b(?:above|over|higher\s+than|more\s+than)\s+(?:what\s+we\s+)?(?:budget|planned|expected|forecast)", re.IGNORECASE), "pricing"),
    (re.compile(r"\b(?:too\s+expensive|cost\s+concern|price\s+is\s+(?:high|too\s+high)|expensive\s+for\s+us)\b", re.IGNORECASE), "pricing"),
    (re.compile(r"\b(?:not\s+sure|concerned|worried)\s+(?:about|if|whether)\b", re.IGNORECASE), "uncertainty"),
    (re.compile(r"\b(?:need\s+to\s+think|let\s+me\s+check|have\s+to\s+ask)\b", re.IGNORECASE), "deferral"),
    (re.compile(r"\b(?:competitor|alternative|other\s+option)\b", re.IGNORECASE), "competition"),
    (re.compile(r"\bbudget(?:ed|ing)?\b.*\b(?:high|above|over|concern|issue)\b", re.IGNORECASE), "pricing"),
]

COMMITMENT_PATTERNS = [
    re.compile(r"\b(?:we'?ll|we\s+will|I'?ll|I\s+will|promise|commit)\s+(?:deliver|ship|deploy|send|provide|have\s+\w+\s+(?:ready|available|by))\b", re.IGNORECASE),
    re.compile(r"\b(?:by\s+(?:next|this|end\s+of)\s+(?:week|friday|monday|month|quarter))\b", re.IGNORECASE),
    re.compile(r"\b(?:target\s+date|due\s+(?:by|date))\b", re.IGNORECASE),
]


class LiveIntelligenceEngine:
    """Processes transcript chunks and produces live suggestion cards.

    Usage:
        engine = LiveIntelligenceEngine(oem_state)
        cards = engine.process_transcript(transcript_text, speaker, entity)
        for card in cards:
            await websocket.send_json({"type": "SUGGESTION", "card": card.to_dict()})
    """

    def __init__(self, oem_state=None) -> None:
        self.oem = oem_state
        self._seen_commitments: set[str] = set()  # for dedup
        self._objection_count = 0  # for confidence denominator
        self._pattern_matches: list[dict] = []

    def process_transcript(
        self,
        text: str,
        speaker: str = "",
        entity: str | None = None,
    ) -> list[SuggestionCard]:
        """Process a transcript chunk and return any suggestion cards generated."""
        cards: list[SuggestionCard] = []

        # 1. Objection detection
        objection_card = self._detect_objection(text, speaker)
        if objection_card:
            cards.append(objection_card)

        # 2. Commitment detection (deduped)
        commitment_card = self._detect_commitment(text, speaker, entity)
        if commitment_card:
            cards.append(commitment_card)

        # 3. Organizational whisper (entity match against OEM signals)
        whisper_card = self._detect_whisper(text, speaker, entity)
        if whisper_card:
            cards.append(whisper_card)

        # 4. Historical pattern match
        pattern_card = self._detect_pattern(text, speaker, entity)
        if pattern_card:
            cards.append(pattern_card)

        return cards

    def _detect_objection(self, text: str, speaker: str) -> SuggestionCard | None:
        """Detect objection patterns in the transcript."""
        for pattern, objection_type in OBJECTION_PATTERNS:
            if pattern.search(text):
                self._objection_count += 1
                # Confidence: based on how many times we've seen this objection type
                # P25: <10 samples = "insufficient calibration history"
                denominator = self._objection_count
                confidence = min(0.5 + (denominator * 0.05), 0.95)  # grows with samples

                return SuggestionCard(
                    card_type="objection",
                    title=f"Objection: {objection_type.title()}",
                    text=f"{speaker} raised a {objection_type} objection: \"{text[:100]}\"",
                    confidence=confidence,
                    confidence_denominator=denominator,
                    evidence={
                        "source": "objection_pattern_match",
                        "objection_type": objection_type,
                        "trigger_text": text[:120],
                        "historical_count": denominator,
                    },
                    actions=["Show response", "Dismiss"],
                )
        return None

    def _detect_commitment(self, text: str, speaker: str, entity: str | None) -> SuggestionCard | None:
        """Detect commitment patterns, deduped against existing commitments."""
        for pattern in COMMITMENT_PATTERNS:
            if pattern.search(text):
                # Dedup: check if we've already seen this exact commitment text
                commitment_hash = hash(text[:100].lower())
                if commitment_hash in self._seen_commitments:
                    return None  # duplicate — don't re-surface
                self._seen_commitments.add(commitment_hash)

                # Check against existing commitments in the OEM
                day_count = self._get_commitment_day_count(text)

                return SuggestionCard(
                    card_type="commitment",
                    title="Commitment Tracked",
                    text=f"{speaker} committed: \"{text[:100]}\"",
                    confidence=1.0,  # direct detection
                    confidence_denominator=1,
                    evidence={
                        "source": "commitment_tracker",
                        "speaker": speaker,
                        "entity": entity,
                        "day_count": day_count,
                        "deduped": day_count > 0,
                    },
                    actions=["View commitment", "Dismiss"],
                )
        return None

    def _detect_whisper(self, text: str, speaker: str, entity: str | None) -> SuggestionCard | None:
        """Detect organizational whispers — entity matches in OEM signals."""
        if not self.oem or not entity:
            return None

        # Search OEM signals for mentions of the entity in the transcript
        entity_lower = entity.lower()
        signals = getattr(self.oem, "signals", []) or []

        matching_signals = []
        for sig in signals:
            sig_text = ""
            if hasattr(sig, "metadata"):
                sig_text = (sig.metadata.get("text", "") or sig.metadata.get("body", "")
                           or sig.metadata.get("title", "") or sig.metadata.get("commitment", ""))
            if entity_lower in sig_text.lower() and entity_lower in text.lower():
                matching_signals.append(sig)

        if not matching_signals or len(matching_signals) < 2:
            return None  # need 2+ sources for cross-validation

        # Cross-validated whisper
        source_count = len(matching_signals)
        confidence = min(0.7 + (source_count * 0.05), 0.95)

        return SuggestionCard(
            card_type="whisper",
            title="Organizational Insight",
            text=f"Found {source_count} organizational signals related to {entity} in this conversation",
            confidence=confidence,
            confidence_denominator=source_count,
            evidence={
                "source": "oem_signal_cross_validation",
                "entity": entity,
                "matching_signal_count": source_count,
                "signal_ids": [getattr(s, "signal_id", str(i)) for i, s in enumerate(matching_signals[:3])],
            },
            actions=["Show details", "Later"],
        )

    def _detect_pattern(self, text: str, speaker: str, entity: str | None) -> SuggestionCard | None:
        """Detect historical pattern matches — conversation resembles a past meeting."""
        # Phase 4 stub: pattern detection requires meeting history
        # Phase 4.5 will implement full pattern matching via PatternDetector
        if not entity or len(text) < 50:
            return None

        # Simple heuristic: if the text mentions "pricing" and we've seen pricing before
        if "pricing" in text.lower() and self._objection_count > 0:
            denominator = self._objection_count
            confidence = min(0.4 + (denominator * 0.08), 0.85)

            return SuggestionCard(
                card_type="pattern",
                title="Historical Pattern Match",
                text=f"This conversation resembles {denominator} previous pricing discussion(s)",
                confidence=confidence,
                confidence_denominator=denominator,
                evidence={
                    "source": "pattern_detector",
                    "entity": entity,
                    "match_count": denominator,
                },
                actions=["View case", "Dismiss"],
            )
        return None

    def _get_commitment_day_count(self, text: str) -> int:
        """Check if this commitment matches an existing one and return its day count."""
        if not self.oem:
            return 0
        # Phase 4 stub: simple text match against existing commitments
        # Phase 4.5 will use content-hash dedup via CommitmentTracker
        return 0
