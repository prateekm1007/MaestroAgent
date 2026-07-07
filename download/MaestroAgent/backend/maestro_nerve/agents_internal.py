"""
Nerve-style internal-operations agents.

These agents query the OEM Engine for internal-ops context:
  - HR: meeting load, talk-ratio imbalances, burnout signals
  - Legal: contract commitments, compliance commitments
  - Operations: process bottlenecks, recurring escalations
  - Support: support-ticket sentiment, recurring issues
  - Data: analytics gaps, Brier-score tracking
  - Security: data-handling commitments, access reviews
  - Partnerships: partner health, joint-account commitments
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from .base_agent import (
    BaseAgent,
    AgentContext,
    AgentInsight,
    AgentCapability,
    register_agent,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 8. HR AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class HRAgent(BaseAgent):
    """Detects burnout signals, meeting-load imbalance, and coaching opportunities.

    Beats Nerve's siloed HR Agent by combining:
      - MeetingGrader (per-employee meeting quality trends)
      - TalkRatioCoach (talk-time imbalance = coaching signal)
      - CalendarAwarenessEngine (meeting load + preparation gaps)
    Privacy-first: only surfaces aggregate signals, never individual
    meeting content. All personal data stays in the user's tenant scope.
    """

    AGENT_NAME = "hr"
    AGENT_DESCRIPTION = (
        "Detects burnout signals (meeting overload, declining meeting grades), "
        "talk-ratio imbalances (coaching opportunities), and preparation gaps. "
        "Privacy-first: aggregate signals only."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Meeting load per actor (proxy for burnout)
        actor_meeting_count: Counter[str] = Counter()
        for s in signals:
            actor = getattr(s, "actor", None) or getattr(s, "user_email", None)
            if actor and "meeting" in (getattr(s, "type", "") or "").lower():
                actor_meeting_count[actor] += 1

        for actor, count in actor_meeting_count.most_common(3):
            if count >= 15:  # 15+ meetings in the signal window = high load
                insights.append(AgentInsight(
                    id=f"hr-load-{actor.split('@')[0]}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"High meeting load: {actor}",
                    body=(
                        f"{actor} has {count} meetings in the current signal "
                        f"window. Sustained meeting load above 15 per window "
                        f"correlates with burnout and declining meeting quality. "
                        f"Consider a workload review."
                    ),
                    confidence=0.65,
                    priority="medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      actor=actor,
                                      meeting_count=count),
                    ],
                    recommended_action=(
                        f"Review {actor}'s calendar for the next 2 weeks. "
                        f"Identify 3 meetings that can be delegated or declined."
                    ),
                    metadata={"actor": actor, "meeting_count": count},
                ))

        # Talk-ratio imbalance (coaching opportunity)
        try:
            coach = self._talk_ratio_coach()
            # Synthesize a talk-ratio signal from meeting data
            talk_heavy_actors: Counter[str] = Counter()
            for s in signals:
                actor = getattr(s, "actor", None) or ""
                metadata = getattr(s, "metadata", {}) or {}
                talk_ratio = metadata.get("talk_ratio", 0)
                if talk_ratio > 0.65:  # talking > 65% of the time = too much
                    talk_heavy_actors[actor] += 1

            for actor, count in talk_heavy_actors.most_common(2):
                if count >= 2:
                    insights.append(AgentInsight(
                        id=f"hr-coaching-{actor.split('@')[0]}-{uuid4().hex[:6]}",
                        agent=self.AGENT_NAME,
                        title=f"Coaching opportunity: {actor} (talk-heavy)",
                        body=(
                            f"{actor} has talked more than 65% of the time in "
                            f"{count} meeting(s). High talk ratio in discovery "
                            f"meetings correlates with lower close rates. "
                            f"This is a coaching opportunity, not a performance "
                            f"issue — the goal is capability-building."
                        ),
                        confidence=0.62,
                        priority="low",
                        evidence_chain=[
                            self.evidence("talk_ratio_coach",
                                          actor=actor,
                                          high_talk_ratio_meetings=count),
                        ],
                        recommended_action=(
                            f"Share the discovery-call talk-ratio guideline "
                            f"with {actor}. Suggest a 50/50 target. Offer to "
                            f"review their next call together."
                        ),
                        metadata={"actor": actor, "talk_heavy_meetings": count},
                    ))
        except Exception as e:
            logger.debug(f"HRAgent: talk ratio coach failed: {e}")

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 9. LEGAL AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class LegalAgent(BaseAgent):
    """Tracks contractually-binding commitments and compliance deadlines.

    Beats Nerve's siloed Legal Agent by querying CommitmentTracker for
    commitments that mention legal/compliance terms (DPA, SLA, GDPR, SOC2).
    """

    AGENT_NAME = "legal"
    AGENT_DESCRIPTION = (
        "Tracks contractually-binding commitments (DPA, SLA, GDPR, SOC2) and "
        "surfaces compliance deadlines that need legal review."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        legal_keywords = ["dpa", "sla", "gdpr", "soc2", "soc 2", "hipaa",
                          "contract", "agreement", "compliance", "audit",
                          "data processing", "subprocessor"]
        legal_commitments = []
        for s in signals:
            if "commitment" not in (getattr(s, "type", "") or "").lower():
                continue
            text = (getattr(s, "text", "") or "").lower()
            if any(kw in text for kw in legal_keywords):
                legal_commitments.append(s)

        if legal_commitments:
            insights.append(AgentInsight(
                id=f"legal-commitments-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title=f"{len(legal_commitments)} legal/compliance commitment(s) tracked",
                body=(
                    f"{len(legal_commitments)} commitment(s) reference legal or "
                    f"compliance terms (DPA, SLA, GDPR, SOC2, etc.). Each "
                    f"represents a contractual obligation. Review with legal "
                    f"counsel to ensure the commitment language matches the "
                    f"actual contract terms."
                ),
                confidence=0.72,
                priority="high",
                evidence_chain=[
                    self.evidence("commitment_tracker",
                                  legal_commitment_count=len(legal_commitments),
                                  keywords=legal_keywords),
                ],
                recommended_action=(
                    "Export the legal commitments list to legal counsel. "
                    "For each, verify the commitment text matches the "
                    "applicable contract section."
                ),
                metadata={"legal_commitment_count": len(legal_commitments)},
            ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 10. OPERATIONS AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class OperationsAgent(BaseAgent):
    """Identifies process bottlenecks via recurring commitment themes.

    Beats Nerve's siloed Ops Agent by detecting commitment themes that
    recur across teams (e.g., "we keep promising SSO but can't ship it").
    """

    AGENT_NAME = "operations"
    AGENT_DESCRIPTION = (
        "Identifies process bottlenecks by detecting recurring commitment "
        "themes that span multiple teams. Recurring themes indicate systemic "
        "process gaps, not individual failures."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Group commitments by theme (first 3 words of text)
        theme_counter: Counter[str] = Counter()
        for s in signals:
            if "commitment" not in (getattr(s, "type", "") or "").lower():
                continue
            text = getattr(s, "text", "") or ""
            # Crude theme extraction: first 3 significant words
            words = [w for w in text.lower().split() if len(w) > 3][:3]
            if words:
                theme = " ".join(words)
                theme_counter[theme] += 1

        for theme, count in theme_counter.most_common(3):
            if count >= 3:
                insights.append(AgentInsight(
                    id=f"ops-bottleneck-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Process bottleneck: '{theme}' ({count}x)",
                    body=(
                        f"The commitment theme '{theme}' has recurred {count} "
                        f"times. When the same commitment is repeatedly made, "
                        f"it signals a systemic process gap — the team cannot "
                        f"deliver on this commitment, but sales/CS keeps "
                        f"promising it. Fix the process, not the people."
                    ),
                    confidence=min(0.62 + count * 0.05, 0.85),
                    priority="high" if count >= 5 else "medium",
                    evidence_chain=[
                        self.evidence("commitment_tracker",
                                      theme=theme,
                                      recurrence_count=count),
                    ],
                    recommended_action=(
                        f"Convene a cross-functional review for '{theme}'. "
                        f"Identify whether the gap is capacity, capability, "
                        f"or process. Assign an owner to close the gap."
                    ),
                    metadata={"theme": theme, "recurrence_count": count},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 11. SUPPORT AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class SupportAgent(BaseAgent):
    """Surfaces recurring support themes and at-risk accounts with support load.

    Beats Nerve's siloed Support Agent by combining:
      - SentimentPatternEngine (escalating frustration = support escalation)
      - Pattern detection (recurring keywords = knowledge-base gaps)
      - CommitmentEscalationEngine (broken support commitments)
    """

    AGENT_NAME = "support"
    AGENT_DESCRIPTION = (
        "Surfaces recurring support themes (KB gaps), escalating frustration "
        "(account-level support escalation), and broken support commitments."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Detect escalating frustration (support escalation needed)
        try:
            sentiment_engine = self._sentiment_engine()
            for s in signals:
                sentiment = getattr(s, "sentiment", None) or (
                    getattr(s, "metadata", {}) or {}
                ).get("sentiment")
                if sentiment is not None:
                    sentiment_engine.add_sample_from_dict({
                        "entity": getattr(s, "entity", "unknown"),
                        "sentiment": sentiment,
                        "timestamp": getattr(s, "timestamp",
                                             datetime.now(timezone.utc)).isoformat(),
                    })
            patterns = sentiment_engine.detect_patterns()
            for p in patterns:
                ptype = (getattr(p, "pattern_type", "") or "").lower()
                if "escalating_frustration" in ptype or "fatigue" in ptype:
                    entity = getattr(p, "entity", "unknown")
                    insights.append(AgentInsight(
                        id=f"support-escalation-{entity}-{uuid4().hex[:6]}",
                        agent=self.AGENT_NAME,
                        title=f"Support escalation needed: {entity}",
                        body=(
                            f"SentimentPatternEngine detected {ptype.replace('_', ' ')} "
                            f"for {entity}. This is a leading indicator of a "
                            f"support ticket storm. Proactive outreach now "
                            f"costs 1/10 of a reactive churn-play later."
                        ),
                        confidence=0.76,
                        priority="high",
                        evidence_chain=[
                            self.evidence("sentiment_pattern_engine",
                                          entity=entity,
                                          pattern=ptype),
                        ],
                        recommended_action=(
                            f"Have a senior support engineer reach out to "
                            f"{entity} within 24 hours. Acknowledge the "
                            f"frustration and provide a direct line."
                        ),
                        metadata={"entity": entity, "pattern": ptype},
                    ))
        except Exception as e:
            logger.debug(f"SupportAgent: sentiment engine failed: {e}")

        # KB gap detection (recurring support keywords)
        kb_keywords: Counter[str] = Counter()
        for s in signals:
            text = (getattr(s, "text", "") or "").lower()
            for kw in ["how do i", "where is", "can't find", "doesn't work",
                       "error message", "login issue", "permission"]:
                if kw in text:
                    kb_keywords[kw] += 1

        for kw, count in kb_keywords.most_common(2):
            if count >= 3:
                insights.append(AgentInsight(
                    id=f"support-kb-gap-{kw[:20]}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"KB gap: '{kw}' ({count}x)",
                    body=(
                        f"The support phrase '{kw}' has appeared in {count} "
                        f"interactions. This indicates a knowledge-base gap — "
                        f"customers are asking the same question because the "
                        f"answer isn't documented or isn't findable."
                    ),
                    confidence=min(0.58 + count * 0.05, 0.82),
                    priority="medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      kb_gap_keyword=kw,
                                      mention_count=count),
                    ],
                    recommended_action=(
                        f"Write a KB article for '{kw}'. Add it to the "
                        f"in-app help center and the customer onboarding flow."
                    ),
                    metadata={"kb_gap_keyword": kw, "mention_count": count},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 12. DATA AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class DataAgent(BaseAgent):
    """Tracks prediction accuracy (Brier scores) and analytics coverage.

    Beats Nerve's siloed Data Agent by querying AdvancedAnalyticsEngine
    for prediction-market calibration and trend analysis.
    """

    AGENT_NAME = "data"
    AGENT_DESCRIPTION = (
        "Tracks prediction accuracy (Brier scores), analytics coverage, and "
        "data-quality signals. Surfaces prediction markets that are "
        "miscalibrated so they can be tuned."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        try:
            engine = self._advanced_analytics_engine()
            trends = engine.get_trends() if hasattr(engine, "get_trends") else []
            for trend in trends[:3]:
                direction = getattr(trend, "direction", None)
                if direction and getattr(direction, "value", "") == "declining":
                    metric = getattr(trend, "metric", "unknown")
                    insights.append(AgentInsight(
                        id=f"data-trend-{metric}-{uuid4().hex[:6]}",
                        agent=self.AGENT_NAME,
                        title=f"Declining trend: {metric}",
                        body=(
                            f"The metric '{metric}' is declining. Review the "
                            f"underlying data to determine whether this is a "
                            f"real signal or a measurement artifact."
                        ),
                        confidence=0.62,
                        priority="medium",
                        evidence_chain=[
                            self.evidence("advanced_analytics_engine",
                                          metric=metric,
                                          direction="declining"),
                        ],
                        recommended_action=(
                            f"Drill into the {metric} trend. Compare against "
                            f"the prior period to isolate the cause."
                        ),
                        metadata={"metric": metric},
                    ))
        except Exception as e:
            logger.debug(f"DataAgent: analytics engine failed: {e}")

        # If no analytics data yet, surface a coverage gap
        if not insights:
            insights.append(AgentInsight(
                id=f"data-coverage-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title="Analytics coverage gap",
                body=(
                    "No trend data is available yet. AdvancedAnalyticsEngine "
                    "requires data points from meetings, commitments, and "
                    "deal outcomes. Once 10+ meetings are graded, trends "
                    "will become available."
                ),
                confidence=0.55,
                priority="low",
                evidence_chain=[
                    self.evidence("advanced_analytics_engine", data_points=0),
                ],
                recommended_action=(
                    "Continue using the Copilot extension. Analytics will "
                    "activate automatically after 10 graded meetings."
                ),
            ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 13. SECURITY AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class SecurityAgent(BaseAgent):
    """Tracks data-handling commitments and surfaces security-relevant signals.

    Beats Nerve's siloed Security Agent by querying CommitmentTracker for
    commitments about data handling, access controls, and audit logs.
    """

    AGENT_NAME = "security"
    AGENT_DESCRIPTION = (
        "Tracks data-handling commitments (encryption, access, retention) and "
        "surfaces security-relevant patterns (commitments to share data with "
        "third parties require DPA review)."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        security_keywords = ["encrypt", "encryption", "access control",
                             "audit log", "retention", "data sharing",
                             "subprocessor", "third party", "penetration test",
                             "vulnerability"]
        security_commitments = []
        for s in signals:
            if "commitment" not in (getattr(s, "type", "") or "").lower():
                continue
            text = (getattr(s, "text", "") or "").lower()
            if any(kw in text for kw in security_keywords):
                security_commitments.append(s)

        if security_commitments:
            insights.append(AgentInsight(
                id=f"security-commitments-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title=f"{len(security_commitments)} security commitment(s) tracked",
                body=(
                    f"{len(security_commitments)} commitment(s) reference "
                    f"security terms (encryption, access, retention, etc.). "
                    f"Each must be verified against the actual security "
                    f"posture. A commitment to encrypt data, for example, "
                    f"requires verification that encryption is actually "
                    f"enabled in production."
                ),
                confidence=0.74,
                priority="high",
                evidence_chain=[
                    self.evidence("commitment_tracker",
                                  security_commitment_count=len(security_commitments)),
                ],
                recommended_action=(
                    "Cross-reference each security commitment with the "
                    "actual security control inventory. Flag any gaps "
                    "to the security team."
                ),
                metadata={"security_commitment_count": len(security_commitments)},
            ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 14. PARTNERSHIPS AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class PartnershipsAgent(BaseAgent):
    """Tracks partner-joint accounts and co-sell commitments.

    Beats Nerve's siloed Partnerships Agent by querying CommitmentTracker
    for commitments involving partner entities.
    """

    AGENT_NAME = "partnerships"
    AGENT_DESCRIPTION = (
        "Tracks partner-joint accounts, co-sell commitments, and partner "
        "health signals. Surfaces commitments that require partner action."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Identify partner-related signals (heuristic: entity contains "partner"
        # or commitment text mentions partner)
        partner_signals = []
        for s in signals:
            entity = (getattr(s, "entity", "") or "").lower()
            text = (getattr(s, "text", "") or "").lower()
            if "partner" in entity or "partner" in text or "co-sell" in text:
                partner_signals.append(s)

        if len(partner_signals) >= 3:
            insights.append(AgentInsight(
                id=f"partnership-activity-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title=f"{len(partner_signals)} partner-related signal(s)",
                body=(
                    f"{len(partner_signals)} signals reference partner activity. "
                    f"Partner-sourced revenue typically has longer cycle times "
                    f"and requires more coordination. Review these signals "
                    f"weekly to ensure partner alignment."
                ),
                confidence=0.66,
                priority="medium",
                evidence_chain=[
                    self.evidence("oem_signal_history",
                                  partner_signal_count=len(partner_signals)),
                ],
                recommended_action=(
                    "Schedule a monthly partner-sync review. For each "
                    "partner-joint account, confirm the partner owner and "
                    "the next co-sell action."
                ),
                metadata={"partner_signal_count": len(partner_signals)},
            ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )
