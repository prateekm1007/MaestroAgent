"""
Talk Ratio & Communication Coach — speaking time, interruptions, clarity.

Phase 15 of the Ambient Intelligence roadmap (Days 94-103, 40 hours).

REALITY CHECK VERDICT: VERY REALISTIC — build immediately.
  - Speaker diarization is a solved problem (pyannote.audio, 90%+ accuracy)
  - Talk ratio is just counting seconds per speaker (objective, not subjective)
  - Interruption detection is simple (overlap in speech segments)
  - No ML inference required for the core metrics

What it does:
  1. Talk ratio — "You spoke 65% of the time. Aim for 40-60%."
  2. Interruption detection — "You interrupted Sam 3 times."
  3. Clarity scoring — "Your sentences averaged 28 words. Aim for <20."
  4. Coaching suggestions — capability-building, NOT dominance-building

Ethical guard: coaching is for the user only. Never used to make the user
"dominate" the call. The constitution: "The organization becomes more
capable, not more dependent." Suggestions are about clarity and balance,
not about talking more or overpowering others.

DEEPER dimension: multi-layer intelligence (timing + interruptions +
clarity → communication coaching).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class CoachingTone(str, Enum):
    """The tone of the coaching suggestion."""
    ENCOURAGING = "encouraging"      # positive reinforcement
    GENTLE_CORRECTION = "gentle_correction"  # mild course correction
    DIRECT_FEEDBACK = "direct_feedback"  # clear, actionable feedback


@dataclass
class SpeechSegment:
    """A single speech segment from diarization."""
    speaker: str           # "you", "them", or speaker name
    start_time: float      # seconds from call start
    end_time: float        # seconds from call start
    text: str = ""         # transcript text for this segment (for clarity)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class Interruption:
    """A detected interruption."""
    interrupter: str       # who interrupted
    interrupted: str       # who was interrupted
    timestamp: float       # seconds from call start
    severity: str = "medium"  # "low" (slight overlap), "medium" (clear cut-off), "high" (aggressive)

    def to_dict(self) -> dict:
        return {
            "interrupter": self.interrupter,
            "interrupted": self.interrupted,
            "timestamp": self.timestamp,
            "severity": self.severity,
        }


@dataclass
class TalkRatioReport:
    """Full talk ratio + communication coaching report."""
    total_duration: float  # seconds
    speaker_durations: dict[str, float]  # speaker → total speaking time
    talk_ratios: dict[str, float]  # speaker → percentage (0-100)
    interruption_count: int
    interruptions: list[Interruption] = field(default_factory=list)
    clarity_score: float = 0.0  # 0-100
    clarity_factors: dict = field(default_factory=dict)
    coaching_suggestions: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # P25: denominator = number of calls analyzed for calibration
    calibration_denominator: int = 0

    @property
    def confidence_label(self) -> str:
        """P25: confidence display gate."""
        if self.calibration_denominator < 10:
            return "insufficient calibration history"
        return f"calibrated from {self.calibration_denominator} calls"

    def to_dict(self) -> dict:
        return {
            "total_duration": round(self.total_duration, 1),
            "speaker_durations": {k: round(v, 1) for k, v in self.speaker_durations.items()},
            "talk_ratios": {k: round(v, 1) for k, v in self.talk_ratios.items()},
            "interruption_count": self.interruption_count,
            "interruptions": [i.to_dict() for i in self.interruptions],
            "clarity_score": round(self.clarity_score, 1),
            "clarity_factors": self.clarity_factors,
            "coaching_suggestions": self.coaching_suggestions,
            "confidence_label": self.confidence_label,
            "calibration_denominator": self.calibration_denominator,
            "timestamp": self.timestamp.isoformat(),
        }


class TalkRatioCoach:
    """
    Analyzes talk ratio, interruptions, and clarity from speech segments.

    Usage:
        coach = TalkRatioCoach()
        coach.add_segment(SpeechSegment("you", 0, 30, "Let me explain the pricing..."))
        coach.add_segment(SpeechSegment("them", 30, 45, "That's too expensive"))
        coach.add_segment(SpeechSegment("you", 44, 60, "But consider the value..."))  # overlap = interruption

        report = coach.generate_report()
        print(f"Your talk ratio: {report.talk_ratios.get('you', 0):.0f}%")
        print(f"Interruptions: {report.interruption_count}")
        print(f"Clarity: {report.clarity_score:.0f}/100")
    """

    # Ideal talk ratio range (for coaching)
    IDEAL_MIN = 40.0  # % — don't talk too little
    IDEAL_MAX = 60.0  # % — don't talk too much

    # Clarity thresholds
    IDEAL_SENTENCE_LENGTH = 20  # words — longer = less clear
    IDEAL_WORDS_PER_MINUTE = 150  # speaking rate

    def __init__(self):
        self._segments: list[SpeechSegment] = []
        self._calibration_calls: int = 0

    def add_segment(self, segment: SpeechSegment) -> None:
        """Add a speech segment from diarization."""
        self._segments.append(segment)

    def add_segment_from_dict(self, data: dict) -> None:
        """Add a segment from a dict (as received from the browser extension)."""
        segment = SpeechSegment(
            speaker=data.get("speaker", "unknown"),
            start_time=data.get("start_time", 0.0),
            end_time=data.get("end_time", 0.0),
            text=data.get("text", ""),
        )
        self.add_segment(segment)

    def record_call_for_calibration(self) -> None:
        """Record this call for calibration (P25 denominator)."""
        self._calibration_calls += 1

    def generate_report(self) -> TalkRatioReport:
        """Generate the full talk ratio + communication coaching report."""
        if not self._segments:
            return TalkRatioReport(
                total_duration=0,
                speaker_durations={},
                talk_ratios={},
                interruption_count=0,
                clarity_score=0,
                calibration_denominator=self._calibration_calls,
            )

        # Sort segments by start time
        segments = sorted(self._segments, key=lambda s: s.start_time)

        # Calculate total speaking time per speaker
        speaker_durations: dict[str, float] = {}
        for seg in segments:
            speaker_durations[seg.speaker] = speaker_durations.get(seg.speaker, 0) + seg.duration

        total_speaking = sum(speaker_durations.values())
        talk_ratios = {
            speaker: (dur / total_speaking * 100) if total_speaking > 0 else 0
            for speaker, dur in speaker_durations.items()
        }

        # Total call duration (from first segment start to last segment end)
        total_duration = segments[-1].end_time - segments[0].start_time if segments else 0

        # Detect interruptions (overlapping segments from different speakers)
        interruptions = self._detect_interruptions(segments)

        # Clarity scoring
        clarity_score, clarity_factors = self._compute_clarity(segments, total_duration)

        # Coaching suggestions
        suggestions = self._generate_coaching(
            talk_ratios, interruptions, clarity_score, clarity_factors
        )

        return TalkRatioReport(
            total_duration=total_duration,
            speaker_durations=speaker_durations,
            talk_ratios=talk_ratios,
            interruption_count=len(interruptions),
            interruptions=interruptions,
            clarity_score=clarity_score,
            clarity_factors=clarity_factors,
            coaching_suggestions=suggestions,
            calibration_denominator=self._calibration_calls,
        )

    def _detect_interruptions(self, segments: list[SpeechSegment]) -> list[Interruption]:
        """Detect interruptions — overlapping segments from different speakers.

        An interruption occurs when speaker B starts talking before speaker A
        finishes. The severity is based on the overlap duration:
          - < 0.5s overlap: low (natural turn-taking)
          - 0.5-2s overlap: medium (clear cut-off)
          - > 2s overlap: high (aggressive interruption)
        """
        interruptions = []

        for i, seg in enumerate(segments):
            for j in range(i + 1, len(segments)):
                next_seg = segments[j]
                if seg.speaker == next_seg.speaker:
                    continue  # same speaker, not an interruption

                # Check for overlap: next speaker starts before current ends
                if next_seg.start_time < seg.end_time:
                    overlap = seg.end_time - next_seg.start_time
                    if overlap > 0.3:  # minimum 0.3s to count as interruption
                        if overlap > 2.0:
                            severity = "high"
                        elif overlap > 0.5:
                            severity = "medium"
                        else:
                            severity = "low"

                        interruptions.append(Interruption(
                            interrupter=next_seg.speaker,
                            interrupted=seg.speaker,
                            timestamp=next_seg.start_time,
                            severity=severity,
                        ))
                    break  # only count first overlap per segment

        return interruptions

    def _compute_clarity(
        self, segments: list[SpeechSegment], total_duration: float
    ) -> tuple[float, dict]:
        """Compute clarity score (0-100) from transcript text.

        Factors:
          - Average sentence length (shorter = clearer): 40% of score
          - Speaking rate (words per minute): 30% of score
          - Filler word frequency (fewer = clearer): 30% of score
        """
        all_text = " ".join(seg.text for seg in segments if seg.text)
        if not all_text:
            return 50.0, {"note": "no transcript available for clarity analysis"}

        # Sentence length
        sentences = [s.strip() for s in all_text.split(".") if s.strip()]
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
        # Score: ideal is < 20 words; penalty for longer
        sentence_score = max(0, 100 - max(0, avg_sentence_length - self.IDEAL_SENTENCE_LENGTH) * 3)

        # Speaking rate (words per minute)
        word_count = len(all_text.split())
        minutes = total_duration / 60 if total_duration > 0 else 1
        wpm = word_count / minutes
        # Score: ideal is 130-170 wpm; penalty for too fast/slow
        if 130 <= wpm <= 170:
            rate_score = 100
        elif 100 <= wpm <= 200:
            rate_score = 75
        else:
            rate_score = 50

        # Filler words
        fillers = ["um", "uh", "like", "you know", "sort of", "kind of", "basically", "actually"]
        filler_count = sum(all_text.lower().count(f) for f in fillers)
        filler_rate = filler_count / max(1, word_count) * 100  # fillers per 100 words
        # Score: < 2% = excellent, < 5% = good, < 10% = fair, > 10% = poor
        if filler_rate < 2:
            filler_score = 100
        elif filler_rate < 5:
            filler_score = 80
        elif filler_rate < 10:
            filler_score = 60
        else:
            filler_score = 30

        clarity_score = sentence_score * 0.4 + rate_score * 0.3 + filler_score * 0.3

        factors = {
            "avg_sentence_length": round(avg_sentence_length, 1),
            "words_per_minute": round(wpm, 0),
            "filler_rate": round(filler_rate, 1),
            "sentence_score": round(sentence_score, 0),
            "rate_score": round(rate_score, 0),
            "filler_score": round(filler_score, 0),
        }

        return clarity_score, factors

    def _generate_coaching(
        self,
        talk_ratios: dict[str, float],
        interruptions: list[Interruption],
        clarity_score: float,
        clarity_factors: dict,
    ) -> list[dict]:
        """Generate coaching suggestions.

        Ethical guard: suggestions are about CLARITY and BALANCE, not about
        dominating the conversation. Capability-building, not dominance-building.
        """
        suggestions = []

        # Talk ratio coaching
        your_ratio = talk_ratios.get("you", 0)
        if your_ratio > self.IDEAL_MAX:
            suggestions.append({
                "type": "talk_ratio",
                "tone": CoachingTone.GENTLE_CORRECTION.value,
                "text": f"You spoke {your_ratio:.0f}% of the time. Consider asking more questions to let the other person share their perspective.",
                "evidence": {"source": "talk_ratio", "your_percentage": round(your_ratio, 1), "ideal_max": self.IDEAL_MAX},
            })
        elif your_ratio < self.IDEAL_MIN:
            suggestions.append({
                "type": "talk_ratio",
                "tone": CoachingTone.ENCOURAGING.value,
                "text": f"You spoke only {your_ratio:.0f}% of the time. Your perspective matters — consider sharing more of your thoughts.",
                "evidence": {"source": "talk_ratio", "your_percentage": round(your_ratio, 1), "ideal_min": self.IDEAL_MIN},
            })

        # Interruption coaching
        your_interruptions = [i for i in interruptions if i.interrupter == "you"]
        if len(your_interruptions) >= 2:
            suggestions.append({
                "type": "interruptions",
                "tone": CoachingTone.GENTLE_CORRECTION.value,
                "text": f"You interrupted {len(your_interruptions)} times. Try pausing for a moment after they finish speaking to ensure they're done.",
                "evidence": {"source": "interruption_detection", "count": len(your_interruptions)},
            })

        their_interruptions = [i for i in interruptions if i.interrupter != "you"]
        if len(their_interruptions) >= 3:
            suggestions.append({
                "type": "interruptions",
                "tone": CoachingTone.DIRECT_FEEDBACK.value,
                "text": f"They interrupted {len(their_interruptions)} times — they may have something urgent to say. Consider pausing to ask for their input.",
                "evidence": {"source": "interruption_detection", "count": len(their_interruptions)},
            })

        # Clarity coaching
        if clarity_score < 60:
            avg_len = clarity_factors.get("avg_sentence_length", 0)
            if avg_len > self.IDEAL_SENTENCE_LENGTH:
                suggestions.append({
                    "type": "clarity",
                    "tone": CoachingTone.DIRECT_FEEDBACK.value,
                    "text": f"Your sentences averaged {avg_len:.0f} words. Aim for under 20 — shorter sentences are easier to follow.",
                    "evidence": {"source": "clarity_analysis", "avg_sentence_length": avg_len, "ideal": self.IDEAL_SENTENCE_LENGTH},
                })

            filler_rate = clarity_factors.get("filler_rate", 0)
            if filler_rate > 5:
                suggestions.append({
                    "type": "clarity",
                    "tone": CoachingTone.GENTLE_CORRECTION.value,
                    "text": f"Filler words appeared {filler_rate:.1f} per 100 words. Pausing silently instead of saying 'um' or 'like' increases authority.",
                    "evidence": {"source": "clarity_analysis", "filler_rate": filler_rate},
                })

        # Positive reinforcement
        if clarity_score >= 80 and len(your_interruptions) == 0:
            suggestions.append({
                "type": "positive",
                "tone": CoachingTone.ENCOURAGING.value,
                "text": "Clear communication with no interruptions — excellent balance.",
                "evidence": {"source": "talk_ratio_coach", "clarity_score": round(clarity_score, 1)},
            })

        return suggestions
