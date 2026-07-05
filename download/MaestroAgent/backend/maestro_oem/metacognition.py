"""
Organ #5 — Metacognition: The organization thinking about its own thinking.

"Engineering is making good decisions. Marketing is making good decisions.
The organization as a whole is making poor decisions. Reason: cross-functional
assumptions never converge."

Computes the meta-gap between team-level quality and org-level quality.
When individual teams are smart but the organization is not, the gap is
in coordination — not in individual intelligence.

Builds on contradiction.py + coordination.py.
API: GET /api/oem/metacognition
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class MetacognitionEngine:
    """The organization thinks about its own thinking.

    Metacognition is the ability to reflect on one's own thought processes.
    For an organization, this means: are the individual parts making good
    decisions while the whole makes poor ones? If so, the problem is in
    the connections, not the components.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def analyze(self) -> dict[str, Any]:
        """Analyze the meta-gap between team quality and org quality."""
        team_quality = self._assess_team_quality()
        org_quality = self._assess_org_quality()
        meta_gap = org_quality["score"] - sum(t["score"] for t in team_quality) / max(len(team_quality), 1)

        # Determine the diagnosis
        if meta_gap < -0.2:
            diagnosis = "Individual teams are making good decisions, but the organization as a whole is making poor ones. The problem is in coordination — cross-functional assumptions don't converge."
            recommendation = "Focus on cross-team alignment, not individual team improvement. The intelligence exists; it's not connected."
        elif meta_gap > 0.2:
            diagnosis = "The organization is making better decisions than individual teams. This suggests strong central coordination is compensating for weak team-level judgment."
            recommendation = "Distribute decision-making authority. The coordination overhead is high."
        else:
            diagnosis = "Team-level and organization-level decision quality are aligned. The organization thinks coherently."
            recommendation = "Continue current patterns. The organization's metacognition is healthy."

        return {
            "team_quality": team_quality,
            "org_quality": org_quality,
            "meta_gap": round(meta_gap, 2),
            "diagnosis": diagnosis,
            "recommendation": recommendation,
            "summary": f"Meta-gap: {round(meta_gap, 2)}. " + ("Teams are smart but the org isn't." if meta_gap < -0.2 else "Org is coherent." if abs(meta_gap) < 0.2 else "Central coordination is compensating."),
        }

    def _assess_team_quality(self) -> list[dict[str, Any]]:
        """Assess decision quality per team/domain."""
        team_scores = []
        try:
            kg = self.model.knowledge
            # Group signals by domain
            domain_signals = defaultdict(list)
            for s in self.signals:
                domain = s.metadata.get("domain", "unknown")
                if s.actor:
                    domain_signals[domain].append(s)

            for domain, sigs in domain_signals.items():
                if len(sigs) < 2:
                    continue
                # Proxy: ratio of positive signals (PRs merged, reviews, agreements)
                # to negative signals (conflicts, contradictions)
                from maestro_oem.signal import SignalType
                positive = sum(1 for s in sigs if s.type in (SignalType.PR_MERGED, SignalType.PR_REVIEWED, SignalType.AGREEMENT))
                negative = sum(1 for s in sigs if s.type in (SignalType.CONFLICT, SignalType.ISSUE_BLOCKED))
                total = len(sigs)
                score = positive / max(total, 1)
                team_scores.append({
                    "domain": domain,
                    "score": round(score, 2),
                    "signal_count": total,
                    "positive": positive,
                    "negative": negative,
                    "quality_label": "good" if score > 0.4 else "moderate" if score > 0.2 else "needs attention",
                })
        except Exception as e:
            logger.debug("Team quality assessment failed: %s", e)

        return team_scores[:5] if team_scores else [{"domain": "unknown", "score": 0.5, "signal_count": 0, "positive": 0, "negative": 0, "quality_label": "unknown"}]

    def _assess_org_quality(self) -> dict[str, Any]:
        """Assess organization-level decision quality."""
        try:
            laws = list(self.model.laws.values())
            total = len(laws)
            validated = sum(1 for l in laws if l.status and l.status.value == "validated")
            score = validated / max(total, 1) if total > 0 else 0.3

            # Check for contradictions — they indicate org-level confusion
            from maestro_oem.contradictions import ContradictionDetector
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            detector = ContradictionDetector(self.model, self.signals, graph)
            contradictions = detector.detect_all()
            contradiction_count = len(contradictions)

            # Org quality is reduced by contradictions
            org_score = max(0, score - contradiction_count * 0.1)

            return {
                "score": round(org_score, 2),
                "validated_patterns": validated,
                "total_patterns": total,
                "contradictions": contradiction_count,
                "quality_label": "coherent" if org_score > 0.4 and contradiction_count < 3 else "fragmented" if contradiction_count > 3 else "moderate",
            }
        except Exception as e:
            logger.debug("Org quality assessment failed: %s", e)
            return {"score": 0.3, "validated_patterns": 0, "total_patterns": 0, "contradictions": 0, "quality_label": "unknown"}
