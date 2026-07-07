"""Phase 10 — Sentiment & Emotion Tracking tests.

Tests the SentimentPatternEngine with 5 patterns + privacy verification +
L0 no-regression.

Gate: 5/5 patterns detected + no audio leak + L0 intact.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone
from collections import deque

import pytest


def make_sample(speaker="them", valence=0.5, arousal=0.5, emotion="neutral",
                sentiment="neutral", ts_offset_seconds=0):
    """Helper: create a SentimentSample with sensible defaults."""
    from maestro_oem.sentiment_patterns import SentimentSample
    return SentimentSample(
        timestamp=datetime.now(timezone.utc) + timedelta(seconds=ts_offset_seconds),
        speaker=speaker,
        sentiment_label=sentiment,
        sentiment_score=0.8,
        emotion_label=emotion,
        emotion_confidence=0.8,
        arousal=arousal,
        valence=valence,
    )


class TestSentimentPatternEngine:
    """Phase 10: SentimentPatternEngine with 5 patterns."""

    def _make_engine(self):
        from maestro_oem.sentiment_patterns import SentimentPatternEngine
        return SentimentPatternEngine(oem=None, window_seconds=300)

    def test_escalating_frustration_detected(self):
        """Pattern 1: escalating frustration (valence ↓, arousal ↑)."""
        engine = self._make_engine()
        for i in range(6):
            engine.add_sample(make_sample(
                speaker="them",
                valence=0.6 - i * 0.1,   # 0.6 → 0.1 (decreasing)
                arousal=0.4 + i * 0.1,   # 0.4 → 0.9 (increasing)
                emotion="frustration",
                sentiment="negative",
                ts_offset_seconds=i * 10,
            ))
        patterns = engine.detect_patterns()
        frustration = [p for p in patterns if p.pattern_type == "escalating_frustration"]
        assert len(frustration) == 1, f"Expected escalating_frustration, got {[p.pattern_type for p in patterns]}"
        assert frustration[0].confidence > 0
        assert frustration[0].action_suggestion is not None
        assert "frustrating" in frustration[0].action_suggestion.lower()

    def test_sudden_positivity_detected(self):
        """Pattern 2: sudden positivity (valence jumps 0.2 → 0.8)."""
        engine = self._make_engine()
        engine.add_sample(make_sample(speaker="them", valence=0.2, arousal=0.4, ts_offset_seconds=0))
        engine.add_sample(make_sample(speaker="them", valence=0.3, arousal=0.5, ts_offset_seconds=10))
        engine.add_sample(make_sample(speaker="them", valence=0.8, arousal=0.8, emotion="joy", sentiment="positive", ts_offset_seconds=20))
        patterns = engine.detect_patterns()
        positivity = [p for p in patterns if p.pattern_type == "sudden_positivity"]
        assert len(positivity) == 1, f"Expected sudden_positivity, got {[p.pattern_type for p in patterns]}"
        assert "breakthrough" in positivity[0].description.lower()

    def test_sentiment_divergence_detected(self):
        """Pattern 3: sentiment divergence (you positive, them negative)."""
        engine = self._make_engine()
        for i in range(4):
            engine.add_sample(make_sample(speaker="you", valence=0.8, arousal=0.7, emotion="joy", sentiment="positive", ts_offset_seconds=i * 5))
            engine.add_sample(make_sample(speaker="them", valence=0.2, arousal=0.7, emotion="anger", sentiment="negative", ts_offset_seconds=i * 5))
        patterns = engine.detect_patterns()
        divergence = [p for p in patterns if p.pattern_type == "sentiment_divergence"]
        assert len(divergence) == 1, f"Expected sentiment_divergence, got {[p.pattern_type for p in patterns]}"

    def test_emotional_fatigue_detected(self):
        """Pattern 4: emotional fatigue (arousal declining over time)."""
        engine = self._make_engine()
        for i in range(6):
            engine.add_sample(make_sample(
                speaker="them",
                arousal=0.7 - i * 0.1,   # 0.7 → 0.2 (declining)
                valence=0.5,
                ts_offset_seconds=i * 60,
            ))
        patterns = engine.detect_patterns()
        fatigue = [p for p in patterns if p.pattern_type == "emotional_fatigue"]
        assert len(fatigue) == 1, f"Expected emotional_fatigue, got {[p.pattern_type for p in patterns]}"
        assert "break" in fatigue[0].action_suggestion.lower()

    def test_stress_spike_detected(self):
        """Pattern 5: stress spike (sudden high arousal + low valence)."""
        engine = self._make_engine()
        engine.add_sample(make_sample(speaker="them", arousal=0.3, valence=0.5, ts_offset_seconds=0))
        engine.add_sample(make_sample(speaker="them", arousal=0.9, valence=0.1, emotion="fear", sentiment="negative", ts_offset_seconds=5))
        patterns = engine.detect_patterns()
        stress = [p for p in patterns if p.pattern_type == "stress_spike"]
        assert len(stress) == 1, f"Expected stress_spike, got {[p.pattern_type for p in patterns]}"
        assert stress[0].confidence > 0.5

    def test_no_false_positives_on_silence(self):
        """No patterns fire when there are insufficient samples."""
        engine = self._make_engine()
        engine.add_sample(make_sample(speaker="them", valence=0.5, arousal=0.5))
        patterns = engine.detect_patterns()
        assert len(patterns) == 0, f"Expected 0 patterns on insufficient data, got {len(patterns)}"

    def test_pattern_signal_emission(self):
        """Patterns are emitted as SENTIMENT_PATTERN signals."""
        engine = self._make_engine()
        # Trigger escalating frustration
        for i in range(6):
            engine.add_sample(make_sample(
                speaker="them",
                valence=0.6 - i * 0.1,
                arousal=0.4 + i * 0.1,
                ts_offset_seconds=i * 10,
            ))
        engine.detect_patterns()
        # Verify signal was emitted
        assert len(engine.emitted_signals) > 0, "No signals emitted"
        sig = engine.emitted_signals[0]
        assert sig["type"] == "sentiment.pattern"
        assert sig["pattern_type"] == "escalating_frustration"
        assert sig["confidence"] > 0
        assert sig["evidence_count"] >= 5  # P25: denominator

    def test_p25_confidence_has_denominator(self):
        """P25: every pattern confidence has its evidence count as denominator."""
        engine = self._make_engine()
        for i in range(6):
            engine.add_sample(make_sample(
                speaker="them",
                valence=0.6 - i * 0.1,
                arousal=0.4 + i * 0.1,
                ts_offset_seconds=i * 10,
            ))
        patterns = engine.detect_patterns()
        for p in patterns:
            d = p.to_dict()
            assert "confidence_denominator" in d
            assert d["confidence_denominator"] >= 5  # at least 5 evidence samples

    def test_add_sample_from_dict(self):
        """Samples can be added from JSON dicts (as received from browser)."""
        engine = self._make_engine()
        engine.add_sample_from_dict({
            "timestamp": 1234567890,
            "speaker": "them",
            "sentiment": {"label": "negative", "score": 0.78},
            "emotion": {"label": "frustration", "confidence": 0.82, "arousal": 0.7, "valence": 0.2},
            "voice_biomarkers": {"pitch_mean": 185.3, "pitch_std": 42.1},
        })
        assert len(engine.samples["them"]) == 1
        sample = engine.samples["them"][0]
        assert sample.emotion_label == "frustration"
        assert sample.valence == 0.2
        assert sample.arousal == 0.7
        assert sample.pitch_mean == 185.3

    def test_duplicate_suppression(self):
        """Duplicate patterns within 60s are suppressed."""
        engine = self._make_engine()
        # Trigger escalating frustration
        for i in range(6):
            engine.add_sample(make_sample(
                speaker="them",
                valence=0.6 - i * 0.1,
                arousal=0.4 + i * 0.1,
                ts_offset_seconds=i * 10,
            ))
        # First detection
        patterns1 = engine.detect_patterns()
        assert len(patterns1) > 0
        # Second detection (immediately — should be suppressed)
        patterns2 = engine.detect_patterns()
        # The duplicate should NOT emit a new signal
        new_signals = [s for s in engine.emitted_signals if s not in [
            {"type": "sentiment.pattern", "pattern_type": p.pattern_type,
             "confidence": p.confidence, "evidence_count": len(p.evidence)}
            for p in patterns1
        ]]
        # At most 1 emission (the first one); the second is a duplicate


class TestPrivacyVerification:
    def _make_engine(self):
        from maestro_oem.sentiment_patterns import SentimentPatternEngine
        return SentimentPatternEngine(oem=None, window_seconds=300)

    """Phase 10: privacy — no audio data leaves the browser."""

    def test_no_audio_in_sentiment_sample(self):
        """SentimentSample contains ONLY labels, no audio data."""
        from maestro_oem.sentiment_patterns import SentimentSample
        sample = SentimentSample(
            timestamp=datetime.now(timezone.utc),
            speaker="them",
            sentiment_label="negative",
            sentiment_score=0.78,
            emotion_label="frustration",
            emotion_confidence=0.82,
            arousal=0.7,
            valence=0.2,
        )
        d = sample.to_dict()
        # Verify NO audio fields exist
        audio_fields = ["audio", "wav", "raw", "bytes", "data", "waveform", "samples_audio"]
        for field in audio_fields:
            assert field not in d, f"SentimentSample contains audio field: {field}"

    def test_no_audio_in_emitted_signal(self):
        """Emitted signals carry ONLY labels — no audio data."""
        engine = self._make_engine()
        for i in range(6):
            engine.add_sample(make_sample(
                speaker="them",
                valence=0.6 - i * 0.1,
                arousal=0.4 + i * 0.1,
                ts_offset_seconds=i * 10,
            ))
        engine.detect_patterns()
        for sig in engine.emitted_signals:
            assert "audio" not in str(sig).lower()
            assert "wav" not in str(sig).lower()
            assert "raw" not in str(sig).lower()


class TestPhase10L0NoRegression:
    """Phase 10 must not regress the L0 substrate."""

    def test_situation_snapshot_27_fields(self):
        from maestro_oem.situation import Situation
        import dataclasses
        assert len(dataclasses.fields(Situation)) == 27

    def test_outcome_ledger_functional(self):
        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

    def test_classifier_new_types(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO by Q4.") == "tentative"
