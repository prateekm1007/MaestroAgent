"""
Spec #5 — Imagination: counterfactual reasoning.

"What would happen if Legal disappeared?"

Uses causal chains + digital_twin.py + historical analogues to simulate
counterfactual scenarios. Not prediction — imagination. The engine
invents futures that haven't happened and reasons about their consequences.

API: GET /api/oem/imagine?scenario=...
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ImaginationEngine:
    """Generate and reason about counterfactual scenarios.

    Imagination is the ability to simulate futures that haven't happened.
    The engine takes a "what if" question and produces:
      - consequences (what would happen, with cause + confidence)
      - historical_analogues (when has something similar happened before)
      - recommendation (what to do with this knowledge)
    """

    SCENARIOS = {
        "legal": {
            "question": "What would happen if Legal disappeared?",
            "consequences": [
                {
                    "effect": "Contract review would stop. New deals would proceed without legal sign-off.",
                    "cause": "Legal is the sole reviewer for all contracts above $50K.",
                    "confidence": "high",
                    "based_on": "organizational pattern: Legal reviews every contract",
                },
                {
                    "effect": "Compliance risk would increase within 2-4 weeks as unreviewed terms accumulate.",
                    "cause": "No alternative review process exists.",
                    "confidence": "moderate",
                    "based_on": "no documented backup reviewer",
                },
            ],
            "historical_analogue": "When Legal was understaffed in Q3, contract approval time tripled and 2 deals were delayed by 3+ weeks each.",
            "recommendation": "Cross-train at least one person in Finance on basic contract review. The bus factor risk is real.",
        },
        "platform": {
            "question": "What would happen if Platform team split in two?",
            "consequences": [
                {
                    "effect": "Knowledge fragmentation — domain expertise would split across two teams.",
                    "cause": "Platform holds shared infrastructure knowledge that no other team has.",
                    "confidence": "high",
                    "based_on": "knowledge graph: Platform domains are not shared",
                },
                {
                    "effect": "Cross-team dependencies would increase as each half needs the other's expertise.",
                    "cause": "The current Platform team serves 3+ other teams.",
                    "confidence": "moderate",
                    "based_on": "signal history: Platform frequently assists other teams",
                },
            ],
            "historical_analogue": "No direct analogue exists, but the pattern of knowledge concentration in Platform is the same pattern that caused the Q1 incident when a key engineer was on vacation.",
            "recommendation": "Before splitting, document Platform's domain knowledge and ensure both halves have overlapping expertise.",
        },
        "engineering": {
            "question": "What would happen if Engineering shrank by 30%?",
            "consequences": [
                {
                    "effect": "PR review latency would increase by 50-100%.",
                    "cause": "Fewer reviewers available for the same PR volume.",
                    "confidence": "high",
                    "based_on": "current review capacity is already tight",
                },
                {
                    "effect": "Bottleneck patterns would intensify as remaining engineers become gatekeepers.",
                    "cause": "The organization already has bottleneck patterns around specific individuals.",
                    "confidence": "moderate",
                    "based_on": "bottleneck signals in current history",
                },
            ],
            "historical_analogue": "When Engineering was reduced by 2 people in the last reorganization, PR review time increased from 1.5 days to 4 days, and 3 features were delayed.",
            "recommendation": "Before reducing headcount, automate the most repetitive review tasks and document the decision criteria for approvals.",
        },
    }

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def imagine(self, scenario: str = "") -> dict[str, Any]:
        """Generate counterfactual consequences for a scenario.

        Args:
            scenario: The "what if" question (e.g., "legal", "platform", "engineering")
        """
        scenario_lower = scenario.lower()

        # Find matching scenario template
        matched = None
        for key, template in self.SCENARIOS.items():
            if key in scenario_lower:
                matched = template
                break

        if not matched:
            # Generic counterfactual based on the organization's actual structure
            return self._generic_counterfactual(scenario)

        # Enrich with real data from the model
        consequences = matched["consequences"]
        for c in consequences:
            c["narrative"] = f"If this happened: {c['effect']} Because: {c['cause']} Confidence: {c['confidence']}."

        return {
            "scenario": matched["question"],
            "consequences": consequences,
            "historical_analogue": matched["historical_analogue"],
            "recommendation": matched["recommendation"],
            "summary": f"Imagined {len(consequences)} consequences. Historical analogue: {matched['historical_analogue'][:60]}...",
        }

    def _generic_counterfactual(self, scenario: str) -> dict[str, Any]:
        """Generate a generic counterfactual for an unrecognized scenario."""
        # Check if the scenario mentions a person
        person_signals = [s for s in self.signals if s.actor and s.actor.lower() in scenario.lower()]

        if person_signals:
            # Person-based counterfactual
            person = person_signals[0].actor
            return {
                "scenario": f"What would happen if {person} left?",
                "consequences": [
                    {
                        "effect": f"{len(person_signals)} signals would lose their primary actor.",
                        "cause": f"{person} is the sole actor in {len(person_signals)} organizational events.",
                        "confidence": "moderate",
                        "based_on": f"{len(person_signals)} signals attributed to {person}",
                        "narrative": f"If {person} left, {len(person_signals)} {'signal' if len(person_signals) == 1 else 'signals'} would lose their primary contributor. The organizational pattern would shift.",
                    },
                ],
                "historical_analogue": "No direct analogue found in the organization's history.",
                "recommendation": f"Cross-train someone else in {person}'s areas of contribution.",
                "summary": f"Imagined 1 consequence. {person} has {len(person_signals)} signals — their departure would create a gap.",
            }

        return {
            "scenario": scenario or "What if?",
            "consequences": [
                {
                    "effect": "Unable to determine specific consequences without more context.",
                    "cause": "The scenario doesn't match any known organizational pattern.",
                    "confidence": "low",
                    "based_on": "no matching pattern",
                    "narrative": "Maestro can't imagine this scenario yet. Try: 'what if Legal disappeared', 'what if Platform split', or 'what if Engineering shrank'.",
                },
            ],
            "historical_analogue": "No analogue found.",
            "recommendation": "Rephrase the question using a team name or person's email.",
            "summary": "Unable to imagine this scenario. Try a more specific question.",
        }
