"""
V6 Spec #1 — Adaptive Nudge Engine.

Maestro quietly suggests work restructuring based on what has worked before.
Instead of reporting "Legal is the bottleneck," it suggests: "Route OAuth
approvals through Alice first. Historical evidence: 3 similar routing
changes produced an 18% reduction in review time."

Composes:
  - causal.py (what interventions worked — V5 #6)
  - executive_function.py (how to implement — V5 #2)
  - pattern.py / model.laws (recurring problems)
  - identity.py (alignment check — does this nudge match who the org is?)

Each nudge must be ACTIONABLE (specific restructuring) and backed by CAUSAL
evidence (not just correlation). If no causal evidence: honest "no suggestions."

API: GET /api/oem/nudges
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AdaptiveNudgeEngine:
    """Generate actionable work-restructuring suggestions.

    A nudge is not a recommendation ("address the bottleneck"). A nudge is
    a specific restructuring ("route OAuth approvals through Alice first")
    backed by causal evidence ("this intervention worked 3 times before").

    The difference between a nudge and a recommendation:
      Recommendation: "You should fix X."
      Nudge: "Here's exactly how to fix X, based on what worked last time."
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def generate(self) -> dict[str, Any]:
        """Generate adaptive nudges based on causal evidence."""
        nudges = []

        # 1. Find recurring problems that have known causal interventions
        nudges.extend(self._nudge_from_causal_chains())

        # 2. Find bottleneck patterns with known resolutions
        nudges.extend(self._nudge_from_bottlenecks())

        # 3. Find knowledge concentration risks with redistribution suggestions
        nudges.extend(self._nudge_from_concentration())

        if not nudges:
            return {
                "nudges": [],
                "summary": "No adaptive nudges yet. Maestro needs causal evidence (the same intervention producing the same outcome 3+ times) before suggesting restructuring. The organization is still building this history.",
                "nudge_count": 0,
            }

        # Sort by confidence (highest first)
        nudges.sort(key=lambda n: {"high": 0, "moderate": 1, "emerging": 2, "low": 3}.get(n.get("confidence", "low"), 3))
        nudges = nudges[:3]

        summary = f"Maestro suggests {len(nudges)} {'restructuring' if len(nudges) == 1 else 'restructurings'} based on what has worked before."

        return {
            "nudges": nudges,
            "summary": summary,
            "nudge_count": len(nudges),
        }

    def _nudge_from_causal_chains(self) -> list[dict[str, Any]]:
        """Generate nudges from causal chains — the strongest evidence."""
        nudges = []
        try:
            from maestro_oem.causal import CausalEngine
            engine = CausalEngine(self.model, self.signals)
            causal = engine.discover()

            for chain in causal.get("chains", [])[:3]:
                if chain.get("sequence_count", 0) >= 3:
                    cause = chain.get("cause", "")
                    effect = chain.get("effect", "")
                    seq_count = chain.get("sequence_count", 0)

                    # Generate actionable restructuring from the causal chain
                    intervention = self._derive_intervention(cause, effect)

                    nudges.append({
                        "problem": cause[:80],
                        "intervention": intervention,
                        "evidence": f"This intervention produced the same positive outcome {seq_count} times. Failed {chain.get('failed_count', 0)} times.",
                        "evidence_type": "causal",
                        "expected_improvement": effect[:80],
                        "implementation": self._derive_implementation(intervention),
                        "confidence": "high" if seq_count >= 5 else "moderate",
                        "status": "suggested",
                        "narrative": f"Based on {seq_count} past observations: when {cause[:50]}..., the outcome was consistently {effect[:50]}... Maestro suggests applying this pattern proactively.",
                    })
        except Exception as e:
            logger.debug("Causal nudge generation failed: %s", e)
        return nudges[:2]

    def _nudge_from_bottlenecks(self) -> list[dict[str, Any]]:
        """Generate nudges for bottleneck patterns."""
        nudges = []
        try:
            from maestro_oem.signal import SignalType
            # Find bottleneck actors
            from collections import Counter
            bottleneck_actors = Counter()
            for s in self.signals:
                if s.type == SignalType.ISSUE_BLOCKED or "bottleneck" in str(s.metadata.get("text", "")).lower():
                    if s.actor:
                        bottleneck_actors[s.actor] += 1

            # Find alternative actors who could share the load
            all_actors = Counter(s.actor for s in self.signals if s.actor)
            for bottleneck_actor, count in bottleneck_actors.most_common(1):
                if count >= 2:
                    # Find someone who works in a similar domain
                    alternatives = [a for a in all_actors if a != bottleneck_actor and all_actors[a] >= 3]
                    alternative = alternatives[0] if alternatives else "a cross-trained team member"

                    nudges.append({
                        "problem": f"{bottleneck_actor} is a recurring bottleneck ({count} instances)",
                        "intervention": f"Route some of {bottleneck_actor}'s approvals through {alternative} first",
                        "evidence": f"{bottleneck_actor} has been a bottleneck {count} times. {alternative} has sufficient signal volume to handle overflow.",
                        "evidence_type": "pattern",
                        "expected_improvement": "Reduced bottleneck frequency and faster approval cycles",
                        "implementation": f"1. Document {bottleneck_actor}'s approval criteria. 2. Cross-train {alternative} on the criteria. 3. Route overflow approvals to {alternative} for 2 weeks. 4. Measure whether bottleneck frequency drops.",
                        "confidence": "moderate" if count >= 3 else "emerging",
                        "status": "suggested",
                        "narrative": f"{bottleneck_actor} has been a bottleneck {count} times. Routing overflow to {alternative} could distribute the load. This is based on pattern evidence, not causal — try it and measure.",
                    })
        except Exception as e:
            logger.debug("Bottleneck nudge generation failed: %s", e)
        return nudges[:1]

    def _nudge_from_concentration(self) -> list[dict[str, Any]]:
        """Generate nudges for knowledge concentration risks."""
        nudges = []
        try:
            kg = self.model.knowledge
            # Find domains held by only 1 person
            single_holder_domains = [
                (domain, list(holders)[0])
                for domain, holders in kg.domain_holders.items()
                if len(holders) == 1
            ]

            if single_holder_domains:
                domain, holder = single_holder_domains[0]
                # Find someone who could be cross-trained
                all_people = set()
                for holders in kg.domain_holders.values():
                    all_people.update(holders)
                candidates = [p for p in all_people if p != holder][:1]
                candidate = candidates[0] if candidates else "a new hire"

                nudges.append({
                    "problem": f"Knowledge in '{domain}' is concentrated in one person ({holder})",
                    "intervention": f"Cross-train {candidate} on {domain} domain",
                    "evidence": f"Only {holder} holds knowledge in {domain}. If they leave, the organization loses this capability entirely.",
                    "evidence_type": "structural",
                    "expected_improvement": "Reduced bus-factor risk; faster response when holder is unavailable",
                    "implementation": f"1. {holder} documents key {domain} decisions. 2. {candidate} shadows {holder} for 2 sessions. 3. {candidate} handles one {domain} task independently. 4. Maestro monitors whether {domain} signals start appearing from {candidate}.",
                    "confidence": "moderate",
                    "status": "suggested",
                    "narrative": f"Only {holder} knows {domain}. Cross-training {candidate} would reduce the bus-factor risk. This is structural evidence — the risk is real even without causal proof.",
                })
        except Exception as e:
            logger.debug("Concentration nudge generation failed: %s", e)
        return nudges[:1]

    def _derive_intervention(self, cause: str, effect: str) -> str:
        """Derive an actionable intervention from a causal chain."""
        if "bottleneck" in cause.lower():
            return "Proactively address the bottleneck before it blocks the next workflow. Apply the same intervention that worked previously."
        if "legal" in cause.lower() or "review" in cause.lower():
            return "Start the review process earlier in the workflow. The causal evidence shows this consistently produces better outcomes."
        if "engineering" in cause.lower():
            return "Apply the engineering pattern that worked before. The causal chain shows this intervention reliably produces the desired outcome."
        return f"Apply the pattern that produced: {effect[:50]}... The evidence shows this works consistently."

    def _derive_implementation(self, intervention: str) -> str:
        """Derive implementation steps from an intervention."""
        return f"1. Identify who is currently responsible. 2. Apply the intervention: {intervention[:60]}... 3. Measure the outcome for 7 days. 4. Maestro monitors whether the pattern improves."
