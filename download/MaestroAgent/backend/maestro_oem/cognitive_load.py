"""Cognitive Load Engine — measure and reduce organizational cognitive load.

The biggest moat isn't more intelligence. It's less cognitive load.

Organizations waste enormous attention on:
  - Decision fatigue (too many decisions, no prioritization)
  - Context switching (jumping between unrelated work)
  - Meeting overhead (too many meetings, too little output)
  - Knowledge hunting (spending time finding who knows what)
  - Duplicate thinking (re-solving already-solved problems)
  - Information latency (waiting for information that exists somewhere)
  - Attention fragmentation (too many channels, too many priorities)

Maestro should measure these and reduce them. Every release should lower
Organizational Cognitive Load (OCL).

OCL is a board-level metric. It's computed from:
  - The number of unresolved decisions (decision fatigue)
  - The diversity of domains each person touches (context switching)
  - Meeting volume vs output (meeting overhead)
  - Time-to-expert-finding (knowledge hunting)
  - Duplicate work signals (duplicate thinking)
  - Signal latency (information latency)
  - Channel/recommendation count (attention fragmentation)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class CognitiveLoadEngine:
    """Measures organizational cognitive load (OCL).

    Usage:
        engine = CognitiveLoadEngine(model, signals)
        ocl = engine.compute()
        # ocl = {score, level, factors, recommendations}
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def compute(self) -> dict[str, Any]:
        """Compute the organizational cognitive load.

        Returns:
          - score: 0-100 (higher = more load)
          - level: low | moderate | high | critical
          - factors: breakdown of each load source
          - recommendations: what to do about it
          - trend: improving | stable | declining (if history available)
        """
        factors = {
            "decision_fatigue": self._decision_fatigue(),
            "context_switching": self._context_switching(),
            "meeting_overhead": self._meeting_overhead(),
            "knowledge_hunting": self._knowledge_hunting(),
            "duplicate_thinking": self._duplicate_thinking(),
            "information_latency": self._information_latency(),
            "attention_fragmentation": self._attention_fragmentation(),
        }

        # Weighted sum
        weights = {
            "decision_fatigue": 0.20,
            "context_switching": 0.15,
            "meeting_overhead": 0.10,
            "knowledge_hunting": 0.15,
            "duplicate_thinking": 0.15,
            "information_latency": 0.10,
            "attention_fragmentation": 0.15,
        }

        score = sum(factors[k]["score"] * weights[k] for k in factors)

        if score < 30:
            level = "low"
        elif score < 50:
            level = "moderate"
        elif score < 70:
            level = "high"
        else:
            level = "critical"

        recommendations = self._recommendations(factors, level)

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score": round(score, 1),
            "level": level,
            "factors": factors,
            "recommendations": recommendations,
            "narrative": self._narrative(score, level, factors),
        }

    def _decision_fatigue(self) -> dict[str, Any]:
        """How many unresolved decisions are pending."""
        from maestro_oem.learning_object import LearningObjectType

        # Count active recommendations (decisions owed)
        rec_count = 0
        try:
            from maestro_oem.decision import DecisionEngine
            from maestro_oem.evidence_graph import EvidenceGraph
            eg = EvidenceGraph()
            eg.build_from_model(self.model)
            de = DecisionEngine(self.model, eg)
            rec_count = len(de.get_recommendations())
        except Exception:
            pass

        # Score: 0 recs = 0, 5+ recs = 100
        score = min(100, rec_count * 20)

        return {
            "score": score,
            "detail": f"{rec_count} active recommendations pending decisions",
            "metric": rec_count,
        }

    def _context_switching(self) -> dict[str, Any]:
        """How much are people jumping between unrelated domains."""
        # Count distinct domains per person
        person_domains: dict[str, set[str]] = {}
        for s in self.signals:
            domain = s.metadata.get("domain", "")
            if domain and s.actor:
                person_domains.setdefault(s.actor, set()).add(domain)

        if not person_domains:
            return {"score": 0, "detail": "No domain data", "metric": 0}

        avg_domains = sum(len(d) for d in person_domains.values()) / len(person_domains)
        # 1 domain = 0, 3+ domains = 100
        score = min(100, max(0, (avg_domains - 1) * 50))

        return {
            "score": score,
            "detail": f"Average person touches {avg_domains:.1f} domains",
            "metric": round(avg_domains, 2),
        }

    def _meeting_overhead(self) -> dict[str, Any]:
        """Meeting volume relative to output."""
        from maestro_oem.signal import SignalType

        meetings = sum(1 for s in self.signals if s.type == SignalType.MEETING_COMPLETED
                       or s.type == SignalType.CUSTOMER_MEETING)
        merges = sum(1 for s in self.signals if s.type == SignalType.PR_MERGED)

        if merges == 0:
            ratio = meetings  # All meetings, no output
        else:
            ratio = meetings / merges

        # Score: 0 ratio = 0, 5+ meetings per merge = 100
        score = min(100, ratio * 20)

        return {
            "score": score,
            "detail": f"{meetings} meetings vs {merges} merges (ratio: {ratio:.1f})",
            "metric": round(ratio, 2),
        }

    def _knowledge_hunting(self) -> dict[str, Any]:
        """How hard is it to find who knows what."""
        from maestro_oem.learning_object import LearningObjectType

        # Hidden experts = knowledge is undocumented = hunting is harder
        hidden = sum(1 for lo in self.model.learning_objects.values()
                     if lo.type == LearningObjectType.HIDDEN_EXPERT)

        # Questions asked in Slack = people don't know where to look
        from maestro_oem.signal import SignalType
        questions = sum(1 for s in self.signals if s.type == SignalType.QUESTION_ASKED)

        score = min(100, hidden * 5 + questions * 3)

        return {
            "score": score,
            "detail": f"{hidden} hidden experts, {questions} questions asked",
            "metric": hidden + questions,
        }

    def _duplicate_thinking(self) -> dict[str, Any]:
        """How much duplicate work is happening."""
        from maestro_oem.learning_object import LearningObjectType

        dup = sum(1 for lo in self.model.learning_objects.values()
                  if lo.type == LearningObjectType.DUPLICATE_WORK)

        score = min(100, dup * 25)

        return {
            "score": score,
            "detail": f"{dup} duplicate work signals detected",
            "metric": dup,
        }

    def _information_latency(self) -> dict[str, Any]:
        """How long does it take for signals to arrive."""
        # This is a proxy: if signals are old, latency is high
        now = datetime.now(timezone.utc)
        recent = [s for s in self.signals if s.timestamp > now - timedelta(days=7)]

        if not self.signals:
            return {"score": 50, "detail": "No signals", "metric": 0}

        recent_ratio = len(recent) / len(self.signals)
        # High recent ratio = low latency = low score
        score = min(100, max(0, (1 - recent_ratio) * 100))

        return {
            "score": score,
            "detail": f"{len(recent)}/{len(self.signals)} signals from last 7 days",
            "metric": round(recent_ratio, 2),
        }

    def _attention_fragmentation(self) -> dict[str, Any]:
        """How many channels/priorities are competing for attention."""
        # Count distinct Slack channels
        from maestro_oem.signal import SignalType
        channels = set()
        for s in self.signals:
            if s.type in (SignalType.MESSAGE_SENT, SignalType.THREAD_STARTED,
                          SignalType.DECISION_SIGNAL):
                ch = s.metadata.get("channel", "")
                if ch:
                    channels.add(ch)

        # Count active customers (each is an attention sink)
        customers = set()
        for s in self.signals:
            if s.provider.value == "customer":
                cust = s.metadata.get("customer", "")
                if cust:
                    customers.add(cust)

        total_channels = len(channels) + len(customers)
        score = min(100, total_channels * 10)

        return {
            "score": score,
            "detail": f"{len(channels)} channels + {len(customers)} customers competing for attention",
            "metric": total_channels,
        }

    def _recommendations(self, factors: dict, level: str) -> list[dict[str, Any]]:
        """Generate recommendations to reduce cognitive load."""
        recs = []

        if factors["decision_fatigue"]["score"] > 60:
            recs.append({
                "factor": "decision_fatigue",
                "recommendation": "Batch decisions. Maestro's Morning Brief surfaces only the 3 highest-impact decisions — let the rest wait.",
                "expected_reduction": "15-20% decision load",
            })

        if factors["context_switching"]["score"] > 50:
            recs.append({
                "factor": "context_switching",
                "recommendation": "Group work by domain. Maestro's Organizational GPS shows each person's active domains — consolidate where possible.",
                "expected_reduction": "10-15% context-switch cost",
            })

        if factors["knowledge_hunting"]["score"] > 40:
            recs.append({
                "factor": "knowledge_hunting",
                "recommendation": "Document hidden experts. Maestro identifies who knows what — formalize it to reduce hunting time.",
                "expected_reduction": "20-30% time-to-knowledge",
            })

        if factors["duplicate_thinking"]["score"] > 30:
            recs.append({
                "factor": "duplicate_thinking",
                "recommendation": "Check Maestro's autocomplete before starting new work. It surfaces duplicate-work patterns automatically.",
                "expected_reduction": "100% of detected duplicate effort",
            })

        if factors["attention_fragmentation"]["score"] > 50:
            recs.append({
                "factor": "attention_fragmentation",
                "recommendation": "Consolidate channels. Maestro's Executive Feed filters noise — route attention through it rather than raw channels.",
                "expected_reduction": "25-35% attention fragmentation",
            })

        if not recs:
            recs.append({
                "factor": "overall",
                "recommendation": "Cognitive load is within healthy bounds. Continue monitoring.",
                "expected_reduction": "0%",
            })

        return recs

    def _narrative(self, score: float, level: str, factors: dict) -> str:
        """Generate a one-sentence narrative of the cognitive load."""
        top_factor = max(factors, key=lambda k: factors[k]["score"])
        return (
            f"Organizational cognitive load is {level} ({score:.0f}/100). "
            f"Primary driver: {top_factor.replace('_', ' ')} "
            f"({factors[top_factor]['score']:.0f}). "
            f"{factors[top_factor]['detail']}."
        )
