"""
Sentiment Pattern Engine — Detect emotional patterns in meetings.

Phase 10 of the Ambient Intelligence roadmap (Days 44-53, 40 hours).

Patterns detected:
1. Escalating frustration (sentiment trending negative over time)
2. Sudden positivity (breakthrough moment)
3. Sentiment divergence (disagreement between speakers)
4. Emotional fatigue (arousal declining over time)
5. Stress spikes (sudden high-arousal negative emotion)

Each pattern is emitted as a SignalType.SENTIMENT_PATTERN signal to the OEM.

Privacy-first: this engine receives ONLY sentiment/emotion labels (JSON)
from the browser extension. It NEVER receives audio data. The browser
extracts features locally (OpenSMILE WASM) and classifies emotion locally
(CNN via TensorFlow.js). Only the labels arrive here.

Ethical guard: emotion/sentiment analysis is for the USER's awareness only.
Never used to "win" against the other party. The bright line:
"Maestro helps YOU think better. Maestro does NOT help you manipulate,
surveil, or win against another person."

Scientific foundation: OpenSMILE (88 acoustic features, 500+ papers),
Wav2Vec 2.0 (85-92% lab accuracy), RAVDESS validation (75%+ target).
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class SentimentSample:
    """A single sentiment/emotion measurement.

    Received from the browser extension as JSON. Contains NO audio data —
    only labels derived from local processing (OpenSMILE WASM + CNN).
    """
    timestamp: datetime
    speaker: str          # 'you' or 'them' or speaker name
    sentiment_label: str  # positive, negative, neutral
    sentiment_score: float  # 0.0-1.0 confidence
    emotion_label: str    # joy, sadness, anger, fear, surprise, disgust, neutral
    emotion_confidence: float
    arousal: float        # 0.0 (calm) to 1.0 (excited)
    valence: float        # 0.0 (negative) to 1.0 (positive)
    pitch_mean: Optional[float] = None
    pitch_std: Optional[float] = None
    energy_mean: Optional[float] = None
    speaking_rate: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "speaker": self.speaker,
            "sentiment_label": self.sentiment_label,
            "sentiment_score": self.sentiment_score,
            "emotion_label": self.emotion_label,
            "emotion_confidence": self.emotion_confidence,
            "arousal": self.arousal,
            "valence": self.valence,
        }


@dataclass
class SentimentPattern:
    """A detected sentiment pattern."""
    pattern_type: str  # escalating_frustration, sudden_positivity, etc.
    description: str
    confidence: float
    evidence: list[SentimentSample] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action_suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type,
            "description": self.description,
            "confidence": self.confidence,
            "confidence_denominator": len(self.evidence),  # P25: sample count
            "action_suggestion": self.action_suggestion,
            "timestamp": self.timestamp.isoformat(),
            "evidence_count": len(self.evidence),
            "evidence": [s.to_dict() for s in self.evidence[:3]],  # top 3 samples
        }


class SentimentPatternEngine:
    """
    Detects emotional patterns in real-time meeting sentiment.

    Usage:
        engine = SentimentPatternEngine(oem, window_seconds=300)

        # Add samples as they arrive (from browser extension via WebSocket)
        engine.add_sample(sample)

        # Check for patterns
        patterns = engine.detect_patterns()

        # Patterns are automatically emitted as SENTIMENT_PATTERN signals to OEM

    Privacy: receives ONLY labels (JSON). NEVER receives audio.
    """

    def __init__(
        self,
        oem: Any = None,
        window_seconds: int = 300,  # 5-minute sliding window
    ):
        self.oem = oem
        self.window_seconds = window_seconds

        # Sliding window of samples (per speaker)
        self.samples: dict[str, deque[SentimentSample]] = {
            "you": deque(maxlen=100),
            "them": deque(maxlen=100),
        }

        # Detected patterns (to avoid duplicates)
        self.detected_patterns: list[SentimentPattern] = []
        self.emitted_signals: list[dict] = []  # for testing verification

    def add_sample(self, sample: SentimentSample) -> None:
        """Add a new sentiment sample.

        Called when the browser extension sends a sentiment_update message
        via the WebSocket. The sample contains ONLY labels — no audio data.
        """
        speaker = sample.speaker
        if speaker not in self.samples:
            self.samples[speaker] = deque(maxlen=100)
        self.samples[speaker].append(sample)
        logger.debug(
            "SentimentPatternEngine: added sample for %s (emotion=%s, valence=%.2f, arousal=%.2f)",
            speaker, sample.emotion_label, sample.valence, sample.arousal,
        )

    def add_sample_from_dict(self, data: dict) -> None:
        """Add a sample from a JSON dict (as received from the browser extension).

        Expected format:
        {
            "timestamp": 1234567890,
            "speaker": "them",
            "sentiment": {"label": "negative", "score": 0.78},
            "emotion": {"label": "frustration", "confidence": 0.82, "arousal": 0.7, "valence": 0.2},
            "voice_biomarkers": {"pitch_mean": 185.3, "pitch_std": 42.1, ...}
        }
        """
        ts = data.get("timestamp")
        if isinstance(ts, (int, float)):
            timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        else:
            timestamp = datetime.now(timezone.utc)

        sentiment = data.get("sentiment", {})
        emotion = data.get("emotion", {})
        biomarkers = data.get("voice_biomarkers", {})

        sample = SentimentSample(
            timestamp=timestamp,
            speaker=data.get("speaker", "them"),
            sentiment_label=sentiment.get("label", "neutral"),
            sentiment_score=sentiment.get("score", 0.5),
            emotion_label=emotion.get("label", "neutral"),
            emotion_confidence=emotion.get("confidence", 0.5),
            arousal=emotion.get("arousal", 0.5),
            valence=emotion.get("valence", 0.5),
            pitch_mean=biomarkers.get("pitch_mean"),
            pitch_std=biomarkers.get("pitch_std"),
            energy_mean=biomarkers.get("energy_mean"),
            speaking_rate=biomarkers.get("speaking_rate"),
        )
        self.add_sample(sample)

    def detect_patterns(self) -> list[SentimentPattern]:
        """Detect all patterns in current window.

        Returns the list of newly detected patterns. Each pattern is also
        emitted as a SENTIMENT_PATTERN signal to the OEM (if not a duplicate).
        """
        patterns = []

        # 1. Escalating frustration
        frustration = self._detect_escalating_frustration()
        if frustration:
            patterns.append(frustration)

        # 2. Sudden positivity
        positivity = self._detect_sudden_positivity()
        if positivity:
            patterns.append(positivity)

        # 3. Sentiment divergence
        divergence = self._detect_sentiment_divergence()
        if divergence:
            patterns.append(divergence)

        # 4. Emotional fatigue
        fatigue = self._detect_emotional_fatigue()
        if fatigue:
            patterns.append(fatigue)

        # 5. Stress spike
        stress = self._detect_stress_spike()
        if stress:
            patterns.append(stress)

        # Emit patterns as signals (deduped)
        for pattern in patterns:
            if not self._is_duplicate(pattern):
                self.detected_patterns.append(pattern)
                self._emit_pattern_signal(pattern)

        return patterns

    def _detect_escalating_frustration(self) -> Optional[SentimentPattern]:
        """
        Detect escalating frustration: sentiment trending negative over time.

        Criteria:
        - At least 5 samples in window
        - Valence decreasing (becoming more negative)
        - Arousal increasing (becoming more agitated)
        - Linear regression slope < -0.1 (valence) and > 0.1 (arousal)
        """
        samples = list(self.samples.get("them", []))
        if len(samples) < 5:
            return None

        valences = [s.valence for s in samples]
        arousals = [s.arousal for s in samples]

        valence_slope = self._compute_slope(valences)
        arousal_slope = self._compute_slope(arousals)

        if valence_slope < -0.05 and arousal_slope > 0.05:
            confidence = min(0.9, abs(valence_slope) + abs(arousal_slope))

            return SentimentPattern(
                pattern_type="escalating_frustration",
                description=f"Frustration escalating (valence slope: {valence_slope:.2f}, arousal slope: {arousal_slope:.2f})",
                confidence=confidence,
                evidence=samples[-5:],  # last 5 samples as evidence
                action_suggestion="Acknowledge their concern. Ask: 'I sense this is frustrating. What would help?'",
            )

        return None

    def _detect_sudden_positivity(self) -> Optional[SentimentPattern]:
        """
        Detect sudden positivity: breakthrough moment.

        Criteria:
        - Valence jumps from < 0.4 to > 0.7 in 2 samples
        - Arousal increases (excitement)
        """
        samples = list(self.samples.get("them", []))
        if len(samples) < 3:
            return None

        recent = samples[-3:]
        valence_jump = recent[-1].valence - recent[0].valence
        arousal_jump = recent[-1].arousal - recent[0].arousal

        if recent[0].valence < 0.4 and recent[-1].valence > 0.7 and arousal_jump > 0.2:
            confidence = min(0.95, valence_jump + arousal_jump)

            return SentimentPattern(
                pattern_type="sudden_positivity",
                description=f"Breakthrough moment! Valence jumped from {recent[0].valence:.2f} to {recent[-1].valence:.2f}",
                confidence=confidence,
                evidence=recent,
                action_suggestion="This is a breakthrough! Reinforce what just happened. Ask: 'What changed your mind?'",
            )

        return None

    def _detect_sentiment_divergence(self) -> Optional[SentimentPattern]:
        """
        Detect sentiment divergence: disagreement between speakers.

        Criteria:
        - 'you' and 'them' have opposite valence in same time window
        - Both have high arousal (engaged, not passive)
        """
        you_samples = list(self.samples.get("you", []))
        them_samples = list(self.samples.get("them", []))

        if len(you_samples) < 3 or len(them_samples) < 3:
            return None

        # Get recent samples (last 30 seconds)
        now = datetime.now(timezone.utc)
        recent_you = [s for s in you_samples if (now - s.timestamp).total_seconds() < 30]
        recent_them = [s for s in them_samples if (now - s.timestamp).total_seconds() < 30]

        if not recent_you or not recent_them:
            # Fallback: use last 3 samples each
            recent_you = you_samples[-3:]
            recent_them = them_samples[-3:]

        you_valence = sum(s.valence for s in recent_you) / len(recent_you)
        them_valence = sum(s.valence for s in recent_them) / len(recent_them)
        you_arousal = sum(s.arousal for s in recent_you) / len(recent_you)
        them_arousal = sum(s.arousal for s in recent_them) / len(recent_them)

        valence_diff = abs(you_valence - them_valence)
        both_engaged = you_arousal > 0.5 and them_arousal > 0.5

        if valence_diff > 0.4 and both_engaged:
            confidence = min(0.9, valence_diff)

            return SentimentPattern(
                pattern_type="sentiment_divergence",
                description=f"Disagreement detected. You: valence {you_valence:.2f}, Them: valence {them_valence:.2f}",
                confidence=confidence,
                evidence=recent_you + recent_them,
                action_suggestion="Acknowledge the disagreement. Say: 'I sense we see this differently. Let me understand your perspective.'",
            )

        return None

    def _detect_emotional_fatigue(self) -> Optional[SentimentPattern]:
        """
        Detect emotional fatigue: arousal declining over time.

        Criteria:
        - At least 5 samples
        - Arousal slope < -0.1 (declining)
        - Average arousal in last 3 samples < 0.4
        """
        samples = list(self.samples.get("them", []))
        if len(samples) < 5:
            return None

        arousals = [s.arousal for s in samples]
        arousal_slope = self._compute_slope(arousals)

        recent_avg = sum(arousals[-3:]) / 3

        if arousal_slope < -0.05 and recent_avg < 0.4:
            confidence = min(0.85, abs(arousal_slope) + (0.4 - recent_avg))

            return SentimentPattern(
                pattern_type="emotional_fatigue",
                description=f"Energy dropping (arousal slope: {arousal_slope:.2f}, recent avg: {recent_avg:.2f})",
                confidence=confidence,
                evidence=samples[-5:],
                action_suggestion="Energy is dropping. Suggest a 5-minute break.",
            )

        return None

    def _detect_stress_spike(self) -> Optional[SentimentPattern]:
        """
        Detect stress spikes: sudden high-arousal negative emotion.

        Criteria:
        - Most recent sample has arousal > 0.8 and valence < 0.3
        - Previous sample had arousal < 0.5 (sudden change)
        """
        samples = list(self.samples.get("them", []))
        if len(samples) < 2:
            return None

        current = samples[-1]
        previous = samples[-2]

        if (current.arousal > 0.8 and current.valence < 0.3
                and previous.arousal < 0.5):
            confidence = min(0.9, current.arousal + (0.3 - current.valence))

            return SentimentPattern(
                pattern_type="stress_spike",
                description=f"Stress spike detected (arousal: {current.arousal:.2f}, valence: {current.valence:.2f})",
                confidence=confidence,
                evidence=[previous, current],
                action_suggestion="Pause. Ask: 'What's concerning you right now?'",
            )

        return None

    def _compute_slope(self, values: list[float]) -> float:
        """Compute linear regression slope."""
        n = len(values)
        if n < 2:
            return 0.0

        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _is_duplicate(self, pattern: SentimentPattern) -> bool:
        """Check if this pattern was already detected recently (within 60s)."""
        for existing in self.detected_patterns[-10:]:
            if (existing.pattern_type == pattern.pattern_type
                    and (pattern.timestamp - existing.timestamp).total_seconds() < 60):
                return True
        return False

    def _emit_pattern_signal(self, pattern: SentimentPattern) -> None:
        """Emit pattern as a SENTIMENT_PATTERN signal to the OEM.

        The signal carries ONLY labels — no audio data. This is the privacy
        guarantee: the backend never receives or stores audio.
        """
        try:
            from maestro_oem.signal import ExecutionSignal, SignalType

            signal = ExecutionSignal(
                type=SignalType.SENTIMENT_PATTERN,
                actor="sentiment_engine",
                artifact=f"pattern:{pattern.pattern_type}:{pattern.timestamp.isoformat()}",
                timestamp=pattern.timestamp,
                metadata={
                    "pattern_type": pattern.pattern_type,
                    "description": pattern.description,
                    "confidence": pattern.confidence,
                    "confidence_denominator": len(pattern.evidence),  # P25
                    "action_suggestion": pattern.action_suggestion,
                    "evidence_count": len(pattern.evidence),
                },
            )

            # Record for testing verification
            self.emitted_signals.append({
                "type": signal.type.value,
                "pattern_type": pattern.pattern_type,
                "confidence": pattern.confidence,
                "evidence_count": len(pattern.evidence),
            })

            # Ingest into OEM if available (sync for testability)
            if self.oem and hasattr(self.oem, "signals"):
                self.oem.signals.append(signal)
            elif self.oem and hasattr(self.oem, "ingest"):
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.oem.ingest(signal))
                    else:
                        loop.run_until_complete(self.oem.ingest(signal))
                except RuntimeError:
                    # No event loop — sync fallback
                    if hasattr(self.oem, "ingest_sync"):
                        self.oem.ingest_sync(signal)

            logger.info(
                "SentimentPatternEngine: emitted %s pattern (confidence=%.2f, evidence=%d)",
                pattern.pattern_type, pattern.confidence, len(pattern.evidence),
            )
        except Exception as e:
            logger.error("SentimentPatternEngine: failed to emit signal: %s", e)
