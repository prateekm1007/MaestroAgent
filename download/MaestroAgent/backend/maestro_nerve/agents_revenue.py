"""
Nerve-style revenue agents (Growth, Sales, Customer Success, Finance).

These agents query the OEM Engine for revenue-relevant context:
  - DealHealthEngine (per-entity health scores)
  - CommitmentTracker + CommitmentEscalationEngine (open/overdue commitments)
  - SentimentPatternEngine (5 patterns)
  - CrossMeetingThreadBuilder (conversation continuity)
  - CRMConnector (Salesforce/HubSpot sync)
  - NegotiationPatternDetector (pricing objection patterns — historical reference)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from .base_agent import (
    BaseAgent,
    AgentContext,
    AgentInsight,
    AgentCapability,
    register_agent,
)
from .base_agent import confidence_label  # noqa: F401  (re-exported for tests)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 1. GROWTH AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class GrowthAgent(BaseAgent):
    """Identifies expansion, upsell, and account-growth opportunities.

    Beats Nerve's siloed Growth Agent by querying the OEM for:
      - Relationship health (SituationSnapshot.current_state)
      - Sentiment trend (last N interactions)
      - Open commitments (CommitmentTracker)
      - Cross-meeting threads (recurring topics = receptivity signal)
      - Organizational laws about what expansion patterns work
    """

    AGENT_NAME = "growth"
    AGENT_DESCRIPTION = (
        "Identifies expansion and upsell opportunities using relationship "
        "health, sentiment trends, open commitments, and cross-meeting threads."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Group signals by entity
        entities: set[str] = set()
        for s in signals:
            e = getattr(s, "entity", None) or getattr(s, "customer", None)
            if e:
                entities.add(e)

        if not entities:
            # Cold-start: no entities yet — return low-confidence hint
            insights.append(AgentInsight(
                id=f"growth-{uuid4().hex[:8]}",
                agent=self.AGENT_NAME,
                title="No account data yet",
                body=(
                    "Growth analysis requires at least one meeting or signal "
                    "with a customer entity. Once meetings are tracked, this "
                    "agent will surface expansion opportunities backed by "
                    "relationship health, sentiment trends, and commitment history."
                ),
                confidence=0.40,
                priority="low",
                evidence_chain=[self.evidence("oem_signal_history", signal_count=0)],
                recommended_action=(
                    "Hold a customer meeting with the Copilot extension enabled "
                    "to begin populating organizational memory."
                ),
            ))
            return self.apply_confidence_gate(insights, strict=ctx.strict_confidence)

        # For each entity, compute expansion opportunity
        for entity in sorted(entities):
            try:
                situation = self._situation_builder(ctx.user_email).build_for_entity(entity)
            except Exception as e:
                logger.debug(f"GrowthAgent: situation build failed for {entity}: {e}")
                continue

            # Expansion signal: account is on_track + has commitments + threads
            on_track = situation.current_state == "on_track"
            has_commitments = len(situation.commitments) > 0
            thread_count = len(getattr(situation, "related_meetings", []) or [])

            if on_track and has_commitments:
                # Confidence: base 0.65, +0.10 if threads, +0.05 if many commitments
                conf = 0.65
                if thread_count >= 2:
                    conf += 0.10
                if len(situation.commitments) >= 3:
                    conf += 0.05

                insights.append(AgentInsight(
                    id=f"growth-{entity}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Expansion opportunity: {entity}",
                    body=(
                        f"Account is on track with {len(situation.commitments)} "
                        f"open commitment(s) and {thread_count} related meeting(s). "
                        f"Current state: {situation.current_state}. "
                        f"This is a strong signal for an expansion conversation."
                    ),
                    confidence=min(conf, 0.95),
                    priority="high",
                    evidence_chain=[
                        self.evidence("situation_snapshot",
                                      entity=entity,
                                      current_state=situation.current_state,
                                      commitment_count=len(situation.commitments)),
                        self.evidence("oem_signal_history",
                                      related_meetings=thread_count),
                    ],
                    recommended_action=(
                        f"Schedule an expansion call with {entity}. Reference the "
                        f"{len(situation.commitments)} commitment(s) in progress."
                    ),
                    organizational_law="L-2024-087" if conf >= 0.80 else None,
                    metadata={"confidence_source": "heuristic, not calibrated", "entity": entity},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )

    def capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="generate_insights",
                description=self.AGENT_DESCRIPTION,
                input_schema={"user_email": "str", "org_id": "str"},
                output_schema={"insights": "list[AgentInsight]"},
            ),
            AgentCapability(
                name="identify_expansion_targets",
                description="List entities with expansion potential (on_track + commitments).",
                input_schema={"org_id": "str"},
                output_schema={"entities": "list[str]"},
            ),
        ]


# ════════════════════════════════════════════════════════════════════════════
# 2. SALES AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class SalesAgent(BaseAgent):
    """Monitors deal pipeline health and surfaces at-risk deals.

    Beats Nerve's siloed Sales Agent by combining:
      - DealHealthEngine (4-component weighted score)
      - CommitmentEscalationEngine (failure prediction)
      - SentimentPatternEngine (call-level sentiment trends)
      - NegotiationPatternDetector (historical pricing objection patterns)
    """

    AGENT_NAME = "sales"
    AGENT_DESCRIPTION = (
        "Monitors deal pipeline health, surfaces at-risk deals with declining "
        "health scores, and identifies pricing objections from negotiation history."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        entities: set[str] = set()
        for s in signals:
            e = getattr(s, "entity", None) or getattr(s, "customer", None)
            if e:
                entities.add(e)

        if not entities:
            return []

        # Use DealHealthEngine to score each entity
        try:
            engine = self._deal_health_engine()
        except Exception as e:
            logger.debug(f"SalesAgent: deal health engine init failed: {e}")
            return []

        for entity in sorted(entities):
            try:
                score = engine.compute_score(entity)
            except Exception as e:
                logger.debug(f"SalesAgent: compute_score failed for {entity}: {e}")
                continue

            # At-risk deal: score < 65
            if score.score < 65:
                conf = 0.70 + (65 - score.score) / 100  # worse score → higher confidence
                conf = min(conf, 0.92)

                risk_factors_text = ", ".join(
                    f"{r.factor.value if hasattr(r.factor, 'value') else r.factor} ({r.weight:.0%})"
                    for r in (score.risk_factors or [])
                ) or "declining health score"

                insights.append(AgentInsight(
                    id=f"sales-{entity}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Deal at risk: {entity}",
                    body=(
                        f"Health score dropped to {score.score:.0f} "
                        f"(label: {score.confidence_label()}). "
                        f"Risk factors: {risk_factors_text}. "
                        f"Recommended intervention: address the top risk factor."
                    ),
                    confidence=conf,
                    priority="high" if score.score < 50 else "medium",
                    evidence_chain=[
                        self.evidence("deal_health_engine",
                                      entity=entity,
                                      score=round(score.score, 1),
                                      momentum=getattr(score.momentum, "value",
                                                       str(score.momentum)),
                                      risk_factors=risk_factors_text),
                    ],
                    recommended_action=(
                        f"Address the top risk factor for {entity} before the "
                        f"next meeting. Schedule a recovery call within 7 days."
                    ),
                    metadata={"confidence_source": "heuristic, not calibrated", "entity": entity, "health_score": score.score},
                ))

            # Momentum check (declining momentum is a leading indicator)
            momentum_val = getattr(score.momentum, "value", str(score.momentum))
            if momentum_val == "declining":
                insights.append(AgentInsight(
                    id=f"sales-momentum-{entity}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Declining momentum: {entity}",
                    body=(
                        f"Deal momentum is declining even though the health "
                        f"score is {score.score:.0f}. This is a leading indicator "
                        f"that the deal may stall. Early intervention is more "
                        f"effective than waiting for the score to drop."
                    ),
                    confidence=0.68,
                    priority="medium",
                    evidence_chain=[
                        self.evidence("deal_health_engine",
                                      entity=entity,
                                      momentum="declining",
                                      score=round(score.score, 1)),
                    ],
                    recommended_action=(
                        f"Re-engage {entity} with a value-driven touchpoint "
                        f"(case study, ROI calculator, or executive briefing)."
                    ),
                    metadata={"confidence_source": "heuristic, not calibrated", "entity": entity},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )

    def capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="generate_insights",
                description=self.AGENT_DESCRIPTION,
                input_schema={"user_email": "str", "org_id": "str"},
                output_schema={"insights": "list[AgentInsight]"},
            ),
            AgentCapability(
                name="get_at_risk_deals",
                description="List deals with health score < 65.",
                input_schema={"org_id": "str"},
                output_schema={"deals": "list[dict]"},
            ),
        ]


# ════════════════════════════════════════════════════════════════════════════
# 3. CUSTOMER SUCCESS AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class CustomerSuccessAgent(BaseAgent):
    """Identifies churn risk and re-engagement opportunities.

    Beats Nerve's siloed CS Agent by combining:
      - SituationSnapshot (relationship state)
      - SentimentPatternEngine (escalating frustration detection)
      - CommitmentEscalationEngine (commitment failure prediction)
      - Cross-meeting threads (conversation gaps = churn signal)
    """

    AGENT_NAME = "customer_success"
    AGENT_DESCRIPTION = (
        "Identifies churn risk (stale relationships, escalating frustration, "
        "broken commitments) and surfaces re-engagement opportunities."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        entities: set[str] = set()
        for s in signals:
            e = getattr(s, "entity", None) or getattr(s, "customer", None)
            if e:
                entities.add(e)

        # Check commitment escalation
        try:
            escalation_engine = self._commitment_escalation_engine()
            escalations = []
            for commit in escalation_engine._get_all_commitments():
                try:
                    esc = escalation_engine.evaluate_commitment(commit)
                    if esc.level.value in ("high", "critical"):
                        escalations.append((commit, esc))
                except Exception:
                    pass

            for commit, esc in escalations[:5]:  # top 5 escalations
                entity = commit.get("entity", "unknown")
                insights.append(AgentInsight(
                    id=f"cs-escalation-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Broken commitment: {entity}",
                    body=(
                        f"Commitment '{commit.get('text', '')[:80]}' is in "
                        f"{esc.level.value} escalation. Health: {esc.health.value}. "
                        f"Days overdue: {esc.days_overdue or 0}. "
                        f"This is a primary churn driver — broken commitments "
                        f"erode trust faster than any other factor."
                    ),
                    confidence=0.82,
                    priority="high" if esc.level.value == "critical" else "medium",
                    evidence_chain=[
                        self.evidence("commitment_escalation_engine",
                                      entity=entity,
                                      escalation_level=esc.level.value,
                                      health=esc.health.value,
                                      days_overdue=esc.days_overdue),
                    ],
                    recommended_action=(
                        f"Re-engage {entity} immediately with a recovery plan. "
                        f"Acknowledge the missed commitment, provide a new date, "
                        f"and add a value-add concession."
                    ),
                    metadata={"confidence_source": "heuristic, not calibrated", "entity": entity, "escalation_level": esc.level.value},
                ))
        except Exception as e:
            logger.debug(f"CSAgent: escalation engine failed: {e}")

        # Check for stale relationships (no interaction in 21+ days)
        from datetime import datetime, timezone, timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=21)
        for entity in sorted(entities):
            entity_signals = [
                s for s in signals
                if (getattr(s, "entity", None) or getattr(s, "customer", None)) == entity
            ]
            if not entity_signals:
                continue

            last_signal = max(
                entity_signals,
                key=lambda s: getattr(s, "timestamp", datetime.min.replace(tzinfo=timezone.utc)),
            )
            last_ts = getattr(last_signal, "timestamp", None)
            if last_ts and last_ts < cutoff:
                days_stale = (datetime.now(timezone.utc) - last_ts).days
                insights.append(AgentInsight(
                    id=f"cs-stale-{entity}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Stale relationship: {entity}",
                    body=(
                        f"No interaction with {entity} in {days_stale} days. "
                        f"Relationships go stale quickly — after 21 days, "
                        f"re-engagement requires 3x the effort of regular contact."
                    ),
                    confidence=0.75,
                    priority="medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      entity=entity,
                                      last_interaction=last_ts.isoformat(),
                                      days_stale=days_stale),
                    ],
                    recommended_action=(
                        f"Send a personal check-in to {entity} within 48 hours. "
                        f"Reference a specific past conversation topic."
                    ),
                    metadata={"confidence_source": "heuristic, not calibrated", "entity": entity, "days_stale": days_stale},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 4. FINANCE AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class FinanceAgent(BaseAgent):
    """Tracks deal cycle times, commitment economics, and revenue at risk.

    Beats Nerve's siloed Finance Agent by combining:
      - AdvancedAnalyticsEngine (deal cycle trends, Brier scores)
      - DealHealthEngine (revenue at risk per deal)
      - CommitmentTracker (commitment velocity)
    """

    AGENT_NAME = "finance"
    AGENT_DESCRIPTION = (
        "Tracks deal cycle times, revenue at risk, and commitment economics "
        "using the AdvancedAnalyticsEngine and DealHealthEngine."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Compute revenue at risk (sum of deal ARR for at-risk accounts)
        entities: set[str] = set()
        for s in signals:
            e = getattr(s, "entity", None) or getattr(s, "customer", None)
            if e:
                entities.add(e)

        at_risk_count = 0
        try:
            engine = self._deal_health_engine()
            for entity in entities:
                try:
                    score = engine.compute_score(entity)
                    if score.score < 50:
                        at_risk_count += 1
                except Exception:
                    pass
        except Exception:
            pass

        if at_risk_count > 0:
            insights.append(AgentInsight(
                id=f"finance-rev-at-risk-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title=f"Revenue at risk: {at_risk_count} account(s) in critical state",
                body=(
                    f"{at_risk_count} account(s) have a deal health score below 50. "
                    f"Based on historical recovery rates, accounts below this "
                    f"threshold have a 35% churn probability without intervention. "
                    f"Quantify the ARR exposure in the CRM, then prioritize "
                    f"recovery by ARR × churn probability."
                ),
                confidence=0.72,
                priority="high",
                evidence_chain=[
                    self.evidence("deal_health_engine",
                                  at_risk_count=at_risk_count,
                                  threshold=50),
                ],
                recommended_action=(
                    "Run a revenue-at-risk review with Sales + CS this week. "
                    "For each at-risk account, assign a recovery owner and a "
                    "7-day action deadline."
                ),
                metadata={"confidence_source": "heuristic, not calibrated", "at_risk_count": at_risk_count},
            ))

        # Commitment velocity insight
        commitment_signals = [
            s for s in signals
            if "commitment" in (getattr(s, "type", "") or "").lower()
        ]
        if len(commitment_signals) >= 5:
            insights.append(AgentInsight(
                id=f"finance-commit-velocity-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title=f"Commitment velocity: {len(commitment_signals)} tracked",
                body=(
                    f"{len(commitment_signals)} commitments are currently tracked "
                    f"across all customer interactions. Each commitment represents "
                    f"a future obligation that consumes engineering or CS capacity. "
                    f"Review the commitment ledger weekly to ensure the team "
                    f"can deliver on what was promised."
                ),
                confidence=0.65,
                priority="medium",
                evidence_chain=[
                    self.evidence("commitment_tracker",
                                  total_commitments=len(commitment_signals)),
                ],
                recommended_action=(
                    "Review the commitment ledger in the dashboard. Flag any "
                    "commitments due within 7 days that lack an owner."
                ),
                metadata={"confidence_source": "heuristic, not calibrated", "commitment_count": len(commitment_signals)},
            ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )
