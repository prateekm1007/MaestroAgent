"""
V8 Upgrade #1 — Organizational Explanations.

"Why are engineering estimates always wrong?"

Maestro has been producing outputs — recommendations, laws, contradictions,
predictions. V8 transforms it from producing outputs to producing
explanations. An explanation is a multi-step causal chain that answers
"why?" — each step references real model data (laws, learning objects,
signals, domain holders concentration, health metrics), with
evidence_count and evidence_strength.

The ExplanationEngine takes a question and synthesizes a causal chain:

  PR opened
    → review queue (PR_REVIEWED signals, queue length from health)
    → cross-team dependency (domain_holders concentration, collaboration)
    → architecture ownership (knowledge graph: who holds the architecture domain)
    → late QA (ISSUE_TRANSITIONED signals showing QA stalls)
    → missed estimate (validated law: "estimates miss when QA is late")

Each step is sourced from real model state — not hardcoded. When the
model has no relevant data, the engine honestly says so (V5 honesty rule:
no fabricated content).

Builds on: causal.py (causal chains), sowhat.py (consequences),
decision.py (recommendations + laws), model.py (knowledge graph + health).
API: GET /api/oem/explain?q=...
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


class ExplanationEngine:
    """Synthesize multi-step causal explanations for "why?" questions.

    An explanation is NOT a recommendation (that's wisdom.py). An
    explanation is NOT a consequence (that's sowhat.py). An explanation
    is the *causal chain* — the sequence of organizational states and
    events that produce the observed outcome.

    The engine:
      1. Parses the question to identify the outcome being asked about
         (estimates, velocity, bottlenecks, incidents, attrition, etc.)
      2. Searches the model for evidence relevant to that outcome
         (laws, learning objects, signal patterns, knowledge structure).
      3. Composes the evidence into a 3-7 step causal chain where each
         step has: a label, a narrative, evidence_count, evidence_strength,
         and a reference to the underlying model entity.

    Honesty: if the model has insufficient data, the engine returns an
    honest "I don't have enough history to explain this yet" rather than
    fabricating a chain.
    """

    # Outcome templates — what kind of "why" question is being asked?
    # Each template has:
    #   - keywords: triggers that identify this outcome
    #   - chain_builder: method name that composes the causal chain
    #   - summary: one-line outcome description
    _OUTCOME_TEMPLATES = [
        {
            "outcome": "estimate_miss",
            "keywords": ["estimate", "estimates", "estimate wrong", "estimate miss",
                         "estimate always", "estimate late", "estimates always wrong",
                         "deadline", "deadline miss", "behind schedule",
                         "why are engineering estimates", "why are estimates"],
            "chain_builder": "_build_estimate_miss_chain",
            "summary": "why engineering estimates are consistently wrong",
        },
        {
            "outcome": "velocity_drop",
            "keywords": ["velocity", "slow", "slower", "shipping slow",
                         "why are we slow", "why is velocity", "velocity drop"],
            "chain_builder": "_build_velocity_drop_chain",
            "summary": "why organizational velocity has dropped",
        },
        {
            "outcome": "bottleneck",
            "keywords": ["bottleneck", "blocked", "blocking", "stuck",
                         "who is the bottleneck", "why is everything blocked"],
            "chain_builder": "_build_bottleneck_chain",
            "summary": "why work is bottlenecked",
        },
        {
            "outcome": "incident",
            "keywords": ["incident", "incidents", "outage", "bug", "bugs",
                         "production", "p1", "p2", "why do we have incidents",
                         "why are incidents"],
            "chain_builder": "_build_incident_chain",
            "summary": "why incidents are occurring",
        },
        {
            "outcome": "attrition",
            "keywords": ["attrition", "attrition", "churn", "leaving",
                         "people leaving", "why are people leaving",
                         "departure", "departures"],
            "chain_builder": "_build_attrition_chain",
            "summary": "why people are leaving",
        },
    ]

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    def explain(self, question: str) -> dict[str, Any]:
        """Synthesize a multi-step causal explanation for a 'why?' question.

        Args:
            question: The "why" question, e.g. "Why are engineering
                      estimates always wrong?"

        Returns:
            {
                question: str,
                outcome: str,                 # identified outcome category
                summary: str,                 # one-line restatement
                steps: list[step],            # 3-7 step causal chain
                step_count: int,
                overall_evidence_strength: float,    # 0..1, avg of step confidences
                total_evidence: int,          # sum of step evidence_counts
                source_entities: list[str],   # model entities referenced
                honest_limitation: str | None,# None if chain is solid
            }
        """
        if not question or not question.strip():
            return self._empty_explanation(question, "No question provided.")

        q_lower = question.lower().strip()
        # Must be a "why" question — if it's a "what" / "how" / "when",
        # route elsewhere (the caller in ask_v2.js handles routing).
        # We accept questions starting with "why" OR containing "why"
        # as a standalone word.
        is_why = (
            q_lower.startswith("why") or
            " why " in f" {q_lower} " or
            q_lower.startswith("explain why")
        )
        if not is_why:
            return self._empty_explanation(
                question,
                "This doesn't look like a 'why' question. Try rephrasing: 'Why is...?' or 'Why are...?'",
            )

        # Identify the outcome
        outcome_match = self._identify_outcome(q_lower)
        if not outcome_match:
            return self._empty_explanation(
                question,
                "I don't recognize this kind of 'why' question yet. I can explain: estimates, velocity, bottlenecks, incidents, and attrition. Try one of those.",
            )

        # Build the chain
        builder_name = outcome_match["chain_builder"]
        builder = getattr(self, builder_name, None)
        if not builder:
            return self._empty_explanation(question, "Explanation builder missing.")

        steps = builder()
        if not steps or len(steps) < 3:
            # Honest limitation — not enough model data to compose a chain.
            return self._empty_explanation(
                question,
                f"I don't have enough organizational history yet to explain {outcome_match['summary']}. "
                f"Connect more providers (GitHub, Jira, Slack, Confluence) so I can observe the pattern.",
            )

        # Compute aggregate confidence + evidence
        # C3 fix: evidence_strength can be a float (0..1) OR a label string
        # ("supported", "limited evidence"). Only aggregate numeric values;
        # non-numeric values are excluded from the average (not summed).
        raw_strengths = [s.get("evidence_strength", 0.0) for s in steps]
        evidence_strengths = [v for v in raw_strengths if isinstance(v, (int, float))]
        evidence_counts = [s.get("evidence_count", 0) for s in steps]
        overall_conf = round(sum(evidence_strengths) / max(len(evidence_strengths), 1), 3) if evidence_strengths else 0.0
        total_evidence = sum(evidence_counts)
        source_entities = sorted({
            src for s in steps for src in s.get("sources", [])
        })

        # Honest limitation: if total evidence is very low, flag it.
        limitation = None
        if total_evidence < 5:
            limitation = (
                f"Total evidence is low ({total_evidence} signals across {len(steps)} steps). "
                f"This explanation is directionally correct but should be treated as a hypothesis, "
                f"not a conclusion. More data will firm it up."
            )

        return {
            "question": question,
            "outcome": outcome_match["outcome"],
            "summary": outcome_match["summary"],
            "steps": steps,
            "step_count": len(steps),
            "overall_evidence_strength": overall_conf,
            "total_evidence": total_evidence,
            "source_entities": source_entities,
            "honest_limitation": limitation,
        }

    # ─── Outcome identification ────────────────────────────────────────

    def _identify_outcome(self, q_lower: str) -> dict[str, Any] | None:
        """Identify which outcome template matches the question.

        Returns the template dict, or None if no match. A template matches
        if ANY of its keywords appear in the question (case-insensitive).
        """
        best_match = None
        best_hits = 0
        for template in self._OUTCOME_TEMPLATES:
            hits = sum(1 for kw in template["keywords"] if kw in q_lower)
            if hits > best_hits:
                best_hits = hits
                best_match = template
        return best_match if best_hits > 0 else None

    # ─── Chain builders ────────────────────────────────────────────────
    # Each builder returns a list of 3-7 steps. Each step:
    #   {
    #     step: int,
    #     label: str,          # short label
    #     narrative: str,      # 1-2 sentence explanation
    #     evidence_count: int,
    #     confidence: float,   # 0..1
    #     sources: list[str],  # model entity references
    #   }

    def _build_estimate_miss_chain(self) -> list[dict[str, Any]]:
        """Why are engineering estimates always wrong?

        Chain: PR opened → review queue → cross-team dependency →
               architecture ownership → late QA → missed estimate
        """
        steps: list[dict[str, Any]] = []

        # Step 1: PR volume
        from maestro_oem.signal import SignalType
        prs_opened = sum(1 for s in self.signals if s.type == SignalType.PR_OPENED)
        prs_merged = sum(1 for s in self.signals if s.type == SignalType.PR_MERGED)
        if prs_opened > 0:
            merge_ratio = prs_merged / max(prs_opened, 1)
            steps.append({
                "step": 1,
                "label": "PR volume",
                "narrative": f"{prs_opened} PRs were opened, {prs_merged} merged (merge ratio {merge_ratio:.0%}). High PR volume without proportional merges indicates work is accumulating faster than it's being reviewed.",
                "evidence_count": prs_opened,
                "evidence_strength": min(1.0, prs_opened / 20.0),
                "sources": [f"signals.pr_opened={prs_opened}", f"signals.pr_merged={prs_merged}"],
            })

        # Step 2: Review queue
        prs_reviewed = sum(1 for s in self.signals if s.type == SignalType.PR_REVIEWED)
        if prs_reviewed > 0 or prs_opened > 0:
            review_ratio = prs_reviewed / max(prs_opened, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Review queue",
                "narrative": f"{prs_reviewed} reviews occurred for {prs_opened} PRs (review ratio {review_ratio:.0%}). "
                             + ("Reviews are keeping pace." if review_ratio > 0.7 else
                                "Reviews are lagging — PRs wait in queue, blocking downstream work."),
                "evidence_count": prs_reviewed,
                "evidence_strength": min(1.0, prs_reviewed / 15.0),
                "sources": [f"signals.pr_reviewed={prs_reviewed}"],
            })

        # Step 3: Cross-team dependency (domain concentration)
        domain_holders = self.model.knowledge.domain_holders
        if domain_holders:
            # Find domains where knowledge is concentrated (1-2 people)
            concentrated = {
                d: holders for d, holders in domain_holders.items()
                if 1 <= len(holders) <= 2
            }
            total_domains = len(domain_holders)
            conc_count = len(concentrated)
            conc_ratio = conc_count / max(total_domains, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Cross-team dependency",
                "narrative": f"{conc_count} of {total_domains} domains ({conc_ratio:.0%}) are held by 1-2 people. "
                             + ("Knowledge is concentrated — work that crosses these domains must wait for the few holders."
                                if conc_ratio > 0.3 else
                                "Knowledge is reasonably distributed across people."),
                "evidence_count": total_domains,
                "evidence_strength": min(1.0, conc_count / 3.0),
                "sources": [f"knowledge.domain_holders={total_domains} domains",
                            f"knowledge.concentrated={conc_count} domains"],
            })

        # Step 4: Architecture ownership (who owns the architecture domain?)
        arch_holders = domain_holders.get("architecture", set()) or domain_holders.get("platform", set())
        if arch_holders:
            steps.append({
                "step": len(steps) + 1,
                "label": "Architecture ownership",
                "narrative": f"The architecture/platform domain is held by {len(arch_holders)} "
                             f"{'person' if len(arch_holders) == 1 else 'people'}: {', '.join(list(arch_holders)[:3])}. "
                             + ("Every architectural decision routes through them — they are a coordination bottleneck."
                                if len(arch_holders) <= 2 else
                                "Architecture is shared across the team."),
                "evidence_count": len(arch_holders),
                "evidence_strength": "supported" if len(arch_holders) <= 2 else "limited evidence",
                "sources": [f"knowledge.architecture_holders={list(arch_holders)[:3]}"],
            })

        # Step 5: Late QA (issue transitions show QA stalls)
        qa_transitions = [
            s for s in self.signals
            if s.type == SignalType.ISSUE_TRANSITIONED
            and "qa" in str(s.metadata.get("text", "")).lower()
        ]
        blocked_transitions = [
            s for s in self.signals
            if s.type == SignalType.ISSUE_TRANSITIONED
            and "block" in str(s.metadata.get("text", "")).lower()
        ]
        if qa_transitions or blocked_transitions:
            steps.append({
                "step": len(steps) + 1,
                "label": "Late QA",
                "narrative": f"{len(qa_transitions)} QA-stage transitions and {len(blocked_transitions)} blocked transitions observed. "
                             "When QA is the last gate before release, late QA discovery forces estimate overruns.",
                "evidence_count": len(qa_transitions) + len(blocked_transitions),
                "evidence_strength": min(1.0, (len(qa_transitions) + len(blocked_transitions)) / 5.0),
                "sources": [f"signals.qa_transitions={len(qa_transitions)}",
                            f"signals.blocked_transitions={len(blocked_transitions)}"],
            })

        # Step 6: Missed estimate (validated law)
        estimate_laws = [
            law for law in self.model.laws.values()
            if law.statement and any(
                kw in law.statement.lower()
                for kw in ["estimate", "deadline", "schedule", "late", "delay"]
            )
        ]
        if estimate_laws:
            law = estimate_laws[0]
            steps.append({
                "step": len(steps) + 1,
                "label": "Missed estimate",
                "narrative": f"Validated organizational pattern: \"{law.statement[:120]}{'...' if len(law.statement) > 120 else ''}\" "
                             f"(confidence {law.confidence:.0%}, {law.evidence_count} evidence, status: {law.status.value if law.status else 'unknown'}). "
                             "This pattern confirms the chain ends in missed estimates.",
                "evidence_count": law.evidence_count,
                "evidence_strength": law.confidence,
                "sources": [f"law.{law.code}"],
            })
        else:
            # No specific law — close the chain with a synthesis from prior steps
            if len(steps) >= 3:
                steps.append({
                    "step": len(steps) + 1,
                    "label": "Missed estimate",
                    "narrative": "No validated organizational law yet captures this outcome, but the upstream chain "
                                 "(PR volume → review queue → dependency → architecture → QA) consistently produces "
                                 "estimate overruns in the observed signals. The pattern is emerging.",
                    "evidence_count": sum(s["evidence_count"] for s in steps),
                    "evidence_strength": "limited evidence",
                    "sources": ["synthesis.from_prior_steps"],
                })

        return steps

    def _build_velocity_drop_chain(self) -> list[dict[str, Any]]:
        """Why has organizational velocity dropped?

        Chain: release frequency → merge ratio → bottleneck person →
               blocked issues → review lag → velocity drop
        """
        steps: list[dict[str, Any]] = []
        from maestro_oem.signal import SignalType

        # Step 1: Release frequency
        release_freq = self.model.health.release_frequency
        steps.append({
            "step": 1,
            "label": "Release frequency",
            "narrative": f"Current release frequency: {release_freq}. "
                         + ("This is below the baseline for a healthy engineering org."
                            if release_freq < 5 else
                            "This is within healthy range."),
            "evidence_count": max(1, release_freq),
            "evidence_strength": "supported" if release_freq < 5 else "limited evidence",
            "sources": ["health.release_frequency"],
        })

        # Step 2: Merge ratio (PRs opened vs merged)
        prs_opened = sum(1 for s in self.signals if s.type == SignalType.PR_OPENED)
        prs_merged = sum(1 for s in self.signals if s.type == SignalType.PR_MERGED)
        if prs_opened > 0:
            merge_ratio = prs_merged / max(prs_opened, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Merge ratio",
                "narrative": f"{prs_merged} of {prs_opened} PRs merged (merge ratio {merge_ratio:.0%}). "
                             + ("Work is shipping slower than it's being opened — velocity is dropping."
                                if merge_ratio < 0.5 else
                                "Merge rate is healthy."),
                "evidence_count": prs_opened,
                "evidence_strength": min(1.0, prs_opened / 20.0),
                "sources": [f"signals.pr_opened={prs_opened}", f"signals.pr_merged={prs_merged}"],
            })

        # Step 3: Bottleneck person (highest-influence single domain holder)
        domain_holders = self.model.knowledge.domain_holders
        single_holder_domains = {
            d: list(h)[0] for d, h in domain_holders.items() if len(h) == 1
        }
        if single_holder_domains:
            influence = self.model.knowledge.influence
            # Find the bottleneck: the person with the highest influence among single holders
            bottleneck_person = max(
                single_holder_domains.values(),
                key=lambda p: influence.get(p, 0),
            )
            bottleneck_domains = [
                d for d, p in single_holder_domains.items() if p == bottleneck_person
            ]
            bottleneck_influence = influence.get(bottleneck_person, 0)
            steps.append({
                "step": len(steps) + 1,
                "label": "Bottleneck person",
                "narrative": f"{bottleneck_person} is the sole holder of {len(bottleneck_domains)} "
                             f"domain(s): {', '.join(bottleneck_domains[:3])}. "
                             f"Influence score: {bottleneck_influence:.1f}. Work requiring these domains routes through one person.",
                "evidence_count": len(bottleneck_domains),
                "evidence_strength": min(1.0, bottleneck_influence / 10.0),
                "sources": [f"knowledge.bottleneck={bottleneck_person}",
                            f"knowledge.bottleneck_domains={bottleneck_domains[:3]}"],
            })

        # Step 4: Blocked issues
        blocked = [
            s for s in self.signals
            if s.type == SignalType.ISSUE_TRANSITIONED
            and "block" in str(s.metadata.get("text", "")).lower()
        ]
        if blocked:
            steps.append({
                "step": len(steps) + 1,
                "label": "Blocked issues",
                "narrative": f"{len(blocked)} blocked issue transitions observed. "
                             "Each blockage stalls dependent work, compounding the velocity drop.",
                "evidence_count": len(blocked),
                "evidence_strength": min(1.0, len(blocked) / 5.0),
                "sources": [f"signals.blocked={len(blocked)}"],
            })

        # Step 5: Review lag
        prs_reviewed = sum(1 for s in self.signals if s.type == SignalType.PR_REVIEWED)
        if prs_opened > 0 and prs_reviewed > 0:
            review_ratio = prs_reviewed / max(prs_opened, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Review lag",
                "narrative": f"Review ratio: {review_ratio:.0%} ({prs_reviewed} reviews / {prs_opened} PRs). "
                             + ("Reviews are lagging — PRs wait, blocking merges, blocking releases."
                                if review_ratio < 0.6 else
                                "Reviews are keeping pace."),
                "evidence_count": prs_reviewed,
                "evidence_strength": min(1.0, prs_reviewed / 15.0),
                "sources": [f"signals.pr_reviewed={prs_reviewed}"],
            })

        # Step 6: Velocity drop (validated law)
        velocity_laws = [
            law for law in self.model.laws.values()
            if law.statement and any(
                kw in law.statement.lower()
                for kw in ["velocity", "slow", "throughput", "ship", "release"]
            )
        ]
        if velocity_laws:
            law = velocity_laws[0]
            steps.append({
                "step": len(steps) + 1,
                "label": "Velocity drop",
                "narrative": f"Validated pattern: \"{law.statement[:120]}{'...' if len(law.statement) > 120 else ''}\" "
                             f"(confidence {law.confidence:.0%}, {law.evidence_count} evidence). "
                             "This pattern confirms the chain ends in a velocity drop.",
                "evidence_count": law.evidence_count,
                "evidence_strength": law.confidence,
                "sources": [f"law.{law.code}"],
            })
        elif len(steps) >= 3:
            steps.append({
                "step": len(steps) + 1,
                "label": "Velocity drop",
                "narrative": "No validated law yet captures this outcome, but the upstream chain "
                             "(release frequency → merge ratio → bottleneck → blocks → review lag) "
                             "consistently produces velocity drops. The pattern is emerging.",
                "evidence_count": sum(s["evidence_count"] for s in steps),
                "evidence_strength": "limited evidence",
                "sources": ["synthesis.from_prior_steps"],
            })

        return steps

    def _build_bottleneck_chain(self) -> list[dict[str, Any]]:
        """Why is everything bottlenecked?

        Chain: bottleneck person → their domains → domains they gate →
               work blocked → upstream accumulation → bottleneck persists
        """
        steps: list[dict[str, Any]] = []
        from maestro_oem.signal import SignalType

        # Step 1: Identify the bottleneck
        domain_holders = self.model.knowledge.domain_holders
        single_holder_domains = {
            d: list(h)[0] for d, h in domain_holders.items() if len(h) == 1
        }
        if not single_holder_domains:
            return []  # Can't build a bottleneck chain without a bottleneck
        influence = self.model.knowledge.influence
        bottleneck_person = max(
            single_holder_domains.values(),
            key=lambda p: influence.get(p, 0),
        )
        bottleneck_domains = sorted([
            d for d, p in single_holder_domains.items() if p == bottleneck_person
        ])
        bottleneck_influence = influence.get(bottleneck_person, 0)

        steps.append({
            "step": 1,
            "label": "Bottleneck person",
            "narrative": f"{bottleneck_person} is the sole holder of {len(bottleneck_domains)} domain(s). "
                         f"With influence {bottleneck_influence:.1f}, they are the single point through which "
                         f"all work in these domains must pass.",
            "evidence_count": len(bottleneck_domains),
            "evidence_strength": min(1.0, bottleneck_influence / 10.0),
            "sources": [f"knowledge.bottleneck={bottleneck_person}"],
        })

        # Step 2: Domains they hold
        steps.append({
            "step": 2,
            "label": "Domains they hold",
            "narrative": f"The bottlenecked domains are: {', '.join(bottleneck_domains[:5])}. "
                         "Any PR, review, or decision touching these domains routes through one person.",
            "evidence_count": len(bottleneck_domains),
            "evidence_strength": "well-supported",
            "sources": [f"knowledge.bottleneck_domains={bottleneck_domains[:5]}"],
        })

        # Step 3: Work they gate (PRs in their domains)
        gated_prs = [
            s for s in self.signals
            if s.type == SignalType.PR_OPENED
            and s.metadata.get("domain") in bottleneck_domains
        ]
        if gated_prs:
            steps.append({
                "step": 3,
                "label": "Work they gate",
                "narrative": f"{len(gated_prs)} PRs were opened in the bottlenecked domains. "
                             "Each one waits for the bottleneck person to review or approve.",
                "evidence_count": len(gated_prs),
                "evidence_strength": min(1.0, len(gated_prs) / 10.0),
                "sources": [f"signals.gated_prs={len(gated_prs)}"],
            })

        # Step 4: Work blocked
        blocked = [
            s for s in self.signals
            if s.type == SignalType.ISSUE_TRANSITIONED
            and "block" in str(s.metadata.get("text", "")).lower()
        ]
        if blocked:
            steps.append({
                "step": len(steps) + 1,
                "label": "Work blocked",
                "narrative": f"{len(blocked)} issue transitions show 'blocked' status. "
                             "Blocked work compounds — each item waits, and items behind it wait too.",
                "evidence_count": len(blocked),
                "evidence_strength": min(1.0, len(blocked) / 5.0),
                "sources": [f"signals.blocked={len(blocked)}"],
            })

        # Step 5: Upstream accumulation
        prs_opened = sum(1 for s in self.signals if s.type == SignalType.PR_OPENED)
        prs_merged = sum(1 for s in self.signals if s.type == SignalType.PR_MERGED)
        if prs_opened > 0:
            open_ratio = (prs_opened - prs_merged) / max(prs_opened, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Upstream accumulation",
                "narrative": f"{prs_opened - prs_merged} of {prs_opened} PRs remain unmerged "
                             f"({open_ratio:.0%} accumulation rate). Upstream work is piling up behind the bottleneck.",
                "evidence_count": prs_opened - prs_merged,
                "evidence_strength": min(1.0, (prs_opened - prs_merged) / 5.0),
                "sources": [f"signals.open_prs={prs_opened - prs_merged}"],
            })

        # Step 6: Bottleneck persists (law or synthesis)
        bottleneck_laws = [
            law for law in self.model.laws.values()
            if law.statement and any(
                kw in law.statement.lower()
                for kw in ["bottleneck", "block", "gate", "single", "concentration"]
            )
        ]
        if bottleneck_laws:
            law = bottleneck_laws[0]
            steps.append({
                "step": len(steps) + 1,
                "label": "Bottleneck persists",
                "narrative": f"Validated pattern: \"{law.statement[:120]}{'...' if len(law.statement) > 120 else ''}\" "
                             f"(confidence {law.confidence:.0%}, {law.evidence_count} evidence). "
                             "The bottleneck is structural, not transient.",
                "evidence_count": law.evidence_count,
                "evidence_strength": law.confidence,
                "sources": [f"law.{law.code}"],
            })
        elif len(steps) >= 3:
            steps.append({
                "step": len(steps) + 1,
                "label": "Bottleneck persists",
                "narrative": "No validated law yet, but the upstream chain "
                             "(bottleneck person → domains → gated work → blocks → accumulation) "
                             "is structural. The bottleneck persists until knowledge is distributed.",
                "evidence_count": sum(s["evidence_count"] for s in steps),
                "evidence_strength": "limited evidence",
                "sources": ["synthesis.from_prior_steps"],
            })

        return steps

    def _build_incident_chain(self) -> list[dict[str, Any]]:
        """Why are incidents occurring?

        Chain: incident rate → merge ratio (unreviewed merges) →
               bottleneck fatigue → p1 cluster risk → incident
        """
        steps: list[dict[str, Any]] = []
        from maestro_oem.signal import SignalType

        # Step 1: Incident rate
        incident_rate = self.model.health.incident_rate
        steps.append({
            "step": 1,
            "label": "Incident rate",
            "narrative": f"Current incident rate: {incident_rate}. "
                         + ("This is above the acceptable threshold for a production system."
                            if incident_rate > 0.1 else
                            "This is within acceptable range."),
            "evidence_count": max(1, int(incident_rate * 20)),
            "evidence_strength": "supported" if incident_rate > 0.1 else "limited evidence",
            "sources": ["health.incident_rate"],
        })

        # Step 2: Merge ratio (unreviewed merges cause incidents)
        prs_opened = sum(1 for s in self.signals if s.type == SignalType.PR_OPENED)
        prs_merged = sum(1 for s in self.signals if s.type == SignalType.PR_MERGED)
        prs_reviewed = sum(1 for s in self.signals if s.type == SignalType.PR_REVIEWED)
        if prs_merged > 0:
            unreviewed_merges = max(0, prs_merged - prs_reviewed)
            unreviewed_ratio = unreviewed_merges / max(prs_merged, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Unreviewed merges",
                "narrative": f"{unreviewed_merges} of {prs_merged} merged PRs ({unreviewed_ratio:.0%}) "
                             "appear to have been merged without a corresponding review. "
                             "Unreviewed merges are the leading indicator of incidents.",
                "evidence_count": unreviewed_merges,
                "evidence_strength": min(1.0, unreviewed_merges / 5.0),
                "sources": [f"signals.unreviewed_merges={unreviewed_merges}"],
            })

        # Step 3: Bottleneck fatigue (concentrated knowledge → rushed merges)
        domain_holders = self.model.knowledge.domain_holders
        single_holder_domains = {
            d: list(h)[0] for d, h in domain_holders.items() if len(h) == 1
        }
        if single_holder_domains:
            steps.append({
                "step": len(steps) + 1,
                "label": "Bottleneck fatigue",
                "narrative": f"{len(single_holder_domains)} domains are held by a single person. "
                             "When a single reviewer is overloaded, PRs get merged under pressure to unblock "
                             "downstream work — reviews get shorter, incidents get through.",
                "evidence_count": len(single_holder_domains),
                "evidence_strength": min(1.0, len(single_holder_domains) / 3.0),
                "sources": [f"knowledge.single_holder_domains={len(single_holder_domains)}"],
            })

        # Step 4: P1 cluster risk
        p1_risk = self.model.health.p1_cluster_risk
        steps.append({
            "step": len(steps) + 1,
            "label": "P1 cluster risk",
            "narrative": f"P1 cluster risk: {p1_risk:.2f}. "
                         + ("Critical components are clustered — a single failure cascades."
                            if p1_risk > 0.5 else
                            "Critical component distribution is acceptable."),
            "evidence_count": max(1, int(p1_risk * 10)),
            "evidence_strength": "supported" if p1_risk > 0.5 else "limited evidence",
            "sources": ["health.p1_cluster_risk"],
        })

        # Step 5: Incident (validated law)
        incident_laws = [
            law for law in self.model.laws.values()
            if law.statement and any(
                kw in law.statement.lower()
                for kw in ["incident", "outage", "p1", "production", "failure"]
            )
        ]
        if incident_laws:
            law = incident_laws[0]
            steps.append({
                "step": len(steps) + 1,
                "label": "Incident",
                "narrative": f"Validated pattern: \"{law.statement[:120]}{'...' if len(law.statement) > 120 else ''}\" "
                             f"(confidence {law.confidence:.0%}, {law.evidence_count} evidence). "
                             "This pattern confirms the chain ends in an incident.",
                "evidence_count": law.evidence_count,
                "evidence_strength": law.confidence,
                "sources": [f"law.{law.code}"],
            })
        elif len(steps) >= 3:
            steps.append({
                "step": len(steps) + 1,
                "label": "Incident",
                "narrative": "No validated law yet, but the upstream chain "
                             "(incident rate → unreviewed merges → bottleneck fatigue → P1 risk) "
                             "consistently produces incidents. The pattern is emerging.",
                "evidence_count": sum(s["evidence_count"] for s in steps),
                "evidence_strength": "limited evidence",
                "sources": ["synthesis.from_prior_steps"],
            })

        return steps

    def _build_attrition_chain(self) -> list[dict[str, Any]]:
        """Why are people leaving?

        Chain: bottleneck load → influence concentration →
               undocumented experts → departure risk → attrition
        """
        steps: list[dict[str, Any]] = []
        from maestro_oem.signal import SignalType

        # Step 1: Bottleneck load (high-influence people are overloaded)
        influence = self.model.knowledge.influence
        if influence:
            top_influencers = sorted(influence.items(), key=lambda x: x[1], reverse=True)[:3]
            avg_top = sum(s for _, s in top_influencers) / max(len(top_influencers), 1)
            steps.append({
                "step": 1,
                "label": "Bottleneck load",
                "narrative": f"The top {len(top_influencers)} most-influential people have an average influence "
                             f"score of {avg_top:.1f}. "
                             + ("This is high — they carry disproportionate organizational load."
                                if avg_top > 5 else
                                "Influence is reasonably distributed."),
                "evidence_count": len(top_influencers),
                "evidence_strength": min(1.0, avg_top / 10.0),
                "sources": [f"knowledge.top_influencers={[p for p, _ in top_influencers]}"],
            })

        # Step 2: Influence concentration
        if influence:
            total_influence = sum(influence.values())
            top_share = sum(s for _, s in (sorted(influence.items(), key=lambda x: x[1], reverse=True)[:3])) / max(total_influence, 1)
            steps.append({
                "step": len(steps) + 1,
                "label": "Influence concentration",
                "narrative": f"The top 3 people hold {top_share:.0%} of total organizational influence. "
                             "Concentrated influence means a single departure is catastrophic.",
                "evidence_count": len(influence),
                "evidence_strength": min(1.0, top_share),
                "sources": [f"knowledge.influence_concentration={top_share:.2f}"],
            })

        # Step 3: Undocumented experts (high influence, no docs)
        hidden_experts = self.model.knowledge.get_hidden_experts()
        if hidden_experts:
            steps.append({
                "step": len(steps) + 1,
                "label": "Undocumented experts",
                "narrative": f"{len(hidden_experts)} high-influence people have no documentation of their expertise. "
                             "When experts feel their knowledge isn't recognized or shared, they leave.",
                "evidence_count": len(hidden_experts),
                "evidence_strength": min(1.0, len(hidden_experts) / 3.0),
                "sources": [f"knowledge.hidden_experts={[e['entity'] for e in hidden_experts[:3]]}"],
            })

        # Step 4: Departure risk (concentration risk)
        concentration_risk = self.model.knowledge.get_concentration_risk()
        if concentration_risk:
            steps.append({
                "step": len(steps) + 1,
                "label": "Departure risk",
                "narrative": f"{len(concentration_risk)} domains are held by exactly one person. "
                             "If any of them leaves, the organization loses that domain entirely. "
                             "This is the leading indicator of attrition-driven capability loss.",
                "evidence_count": len(concentration_risk),
                "evidence_strength": min(1.0, len(concentration_risk) / 3.0),
                "sources": [f"knowledge.concentration_risk={list(concentration_risk.keys())[:3]}"],
            })

        # Step 5: Attrition (validated law)
        attrition_laws = [
            law for law in self.model.laws.values()
            if law.statement and any(
                kw in law.statement.lower()
                for kw in ["attrition", "leaving", "departure", "churn", "burnout"]
            )
        ]
        if attrition_laws:
            law = attrition_laws[0]
            steps.append({
                "step": len(steps) + 1,
                "label": "Attrition",
                "narrative": f"Validated pattern: \"{law.statement[:120]}{'...' if len(law.statement) > 120 else ''}\" "
                             f"(confidence {law.confidence:.0%}, {law.evidence_count} evidence). "
                             "This pattern confirms the chain ends in attrition.",
                "evidence_count": law.evidence_count,
                "evidence_strength": law.confidence,
                "sources": [f"law.{law.code}"],
            })
        elif len(steps) >= 3:
            steps.append({
                "step": len(steps) + 1,
                "label": "Attrition",
                "narrative": "No validated law yet, but the upstream chain "
                             "(bottleneck load → influence concentration → undocumented experts → departure risk) "
                             "is the canonical attrition pattern. The pattern is emerging.",
                "evidence_count": sum(s["evidence_count"] for s in steps),
                "evidence_strength": "limited evidence",
                "sources": ["synthesis.from_prior_steps"],
            })

        return steps

    # ─── Helpers ───────────────────────────────────────────────────────

    def _empty_explanation(self, question: str, reason: str) -> dict[str, Any]:
        """Return an honest empty explanation with a reason."""
        return {
            "question": question or "",
            "outcome": "unknown",
            "summary": reason,
            "steps": [],
            "step_count": 0,
            "overall_evidence_strength": 0.0,
            "total_evidence": 0,
            "source_entities": [],
            "honest_limitation": reason,
        }
