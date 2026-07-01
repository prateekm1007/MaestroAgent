"""
Organ #2 — Curiosity: Maestro asks questions the org has never asked.

Finds untested assumptions, unmeasured domains, unexplained patterns.
Curiosity is not a feature — it's a cognitive organ that makes the
organization question its own blind spots.

The engine scans for:
  1. Untested assumptions — assumptions with 0 contradicting AND 0 supporting signals
  2. Unmeasured domains — knowledge domains with <3 signals (the org isn't watching)
  3. Unexplained patterns — laws with high evidence but no documented explanation
  4. Repeated bottlenecks — the same bottleneck appearing >3 times with no resolution

API: GET /api/oem/curiosity
Returns: {
    questions: [
        {
            question: "We've never measured why Legal rejects OAuth exceptions.",
            type: "unmeasured_domain",
            domain: "legal",
            evidence: "0 signals in the legal domain",
            urgency: "low",
        }
    ],
    summary: "Maestro is curious about 3 things your organization has never investigated.",
    blind_spots: N,
}
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class CuriosityEngine:
    """Find questions the organization has never asked.

    Curiosity is the engine of learning. An organization that stops asking
    questions stops growing. Maestro asks the questions the org doesn't
    know it should ask.
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def generate(self) -> dict[str, Any]:
        """Generate curiosity questions from organizational blind spots."""
        questions = []

        # 1. Untested assumptions
        questions.extend(self._find_untested_assumptions())

        # 2. Unmeasured domains
        questions.extend(self._find_unmeasured_domains())

        # 3. Unexplained patterns
        questions.extend(self._find_unexplained_patterns())

        # 4. Repeated bottlenecks
        questions.extend(self._find_repeated_bottlenecks())

        # Sort by urgency
        questions.sort(key=lambda q: {"high": 0, "medium": 1, "low": 2}.get(q.get("urgency", "low"), 2))

        # Limit to top 5
        questions = questions[:5]

        if len(questions) == 0:
            summary = "Maestro has no open questions. The organization's blind spots are covered."
        else:
            summary = f"Maestro is curious about {len(questions)} {'thing' if len(questions) == 1 else 'things'} your organization has never investigated."

        return {
            "questions": questions,
            "summary": summary,
            "blind_spots": len(questions),
        }

    def _find_untested_assumptions(self) -> list[dict[str, Any]]:
        """Find assumptions with no supporting or contradicting evidence."""
        results = []
        try:
            # Access the assumption graph from the model
            # We check if the OEM state has assumptions via the routes
            from maestro_api.routes.oem import _get_assumption_graph
            graph = _get_assumption_graph()
            all_assumptions = graph.list_assumptions()
            for a in all_assumptions:
                supporting = len(a.get("supporting_signals", []))
                contradicting = len(a.get("contradicting_signals", []))
                if supporting == 0 and contradicting == 0:
                    statement = a.get("statement", "")
                    if len(statement) > 10:
                        results.append({
                            "question": f"Nobody has tested whether '{statement[:60]}...' is true. Should we?",
                            "type": "untested_assumption",
                            "domain": "assumptions",
                            "evidence": "0 supporting, 0 contradicting signals",
                            "urgency": "medium",
                        })
        except Exception as e:
            logger.debug("Untested assumptions scan failed: %s", e)

        return results[:2]

    def _find_unmeasured_domains(self) -> list[dict[str, Any]]:
        """Find knowledge domains with <3 signals — the org isn't watching."""
        results = []
        try:
            kg = self.model.knowledge
            domain_counts = {}
            for domain, holders in kg.domain_holders.items():
                # Count signals per domain
                count = sum(1 for s in self.signals if s.metadata.get("domain", "") == domain)
                domain_counts[domain] = count

            for domain, count in sorted(domain_counts.items(), key=lambda x: x[1]):
                if count < 3 and count > 0:
                    results.append({
                        "question": f"We've only seen {count} {'signal' if count == 1 else 'signals'} from the {domain} domain. Are we paying attention?",
                        "type": "unmeasured_domain",
                        "domain": domain,
                        "evidence": f"{count} signals in {domain}",
                        "urgency": "low" if count > 0 else "medium",
                    })
                elif count == 0:
                    results.append({
                        "question": f"The {domain} domain has zero signals. Is anyone working on this?",
                        "type": "unmeasured_domain",
                        "domain": domain,
                        "evidence": "0 signals",
                        "urgency": "medium",
                    })
        except Exception as e:
            logger.debug("Unmeasured domains scan failed: %s", e)

        return results[:2]

    def _find_unexplained_patterns(self) -> list[dict[str, Any]]:
        """Find laws with high evidence but no documented explanation."""
        results = []
        try:
            for law in self.model.laws.values():
                if law.evidence_count > 5 and not law.outcome:
                    results.append({
                        "question": f"A pattern has appeared {law.evidence_count} times but nobody has explained why. Should we investigate?",
                        "type": "unexplained_pattern",
                        "domain": "patterns",
                        "evidence": f"{law.evidence_count} signals, no documented outcome",
                        "urgency": "high" if law.evidence_count > 10 else "medium",
                    })
        except Exception as e:
            logger.debug("Unexplained patterns scan failed: %s", e)

        return results[:1]

    def _find_repeated_bottlenecks(self) -> list[dict[str, Any]]:
        """Find bottlenecks that keep recurring without resolution."""
        results = []
        try:
            bottleneck_actors = Counter()
            for s in self.signals:
                if s.metadata.get("bottleneck") or "bottleneck" in str(s.metadata.get("text", "")).lower():
                    if s.actor:
                        bottleneck_actors[s.actor] += 1

            for actor, count in bottleneck_actors.most_common(1):
                if count > 3:
                    results.append({
                        "question": f"{actor} has been a bottleneck {count} times. Nobody has investigated why. Should we?",
                        "type": "repeated_bottleneck",
                        "domain": "execution",
                        "evidence": f"{count} bottleneck signals",
                        "urgency": "high",
                    })
        except Exception as e:
            logger.debug("Repeated bottlenecks scan failed: %s", e)

        return results[:1]
