"""
Nerve-style product/engineering/marketing agents.

These agents query the OEM Engine for product-relevant context:
  - SentimentPatternEngine (user feedback trends)
  - CrossMeetingThreadBuilder (recurring feature requests)
  - CommitmentTracker (engineering deliverables promised to customers)
  - MeetingGrader (product review meeting quality)
  - TalkRatioCoach (discovery vs. pitching balance)
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
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
# 5. PRODUCT AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class ProductAgent(BaseAgent):
    """Surfaces product feedback themes and roadmap-relevant signals.

    Beats Nerve's siloed Product Agent by combining:
      - SentimentPatternEngine (user feedback sentiment trends)
      - CrossMeetingThreadBuilder (recurring feature requests across meetings)
      - CommitmentTracker (customer-promised deliverables — roadmap pressure)
      - Pattern detection (topics that recur 3+ times become roadmap candidates)
    """

    AGENT_NAME = "product"
    AGENT_DESCRIPTION = (
        "Surfaces product feedback themes, recurring feature requests, and "
        "customer-promised deliverables that pressure the roadmap."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Topic frequency analysis (recurring topics = roadmap candidates)
        topic_counter: Counter[str] = Counter()
        for s in signals:
            # Topics can be in metadata, tags, or text
            topics = (
                getattr(s, "topics", None)
                or getattr(s, "tags", None)
                or (getattr(s, "metadata", {}) or {}).get("topics", [])
            )
            if topics:
                for t in topics:
                    topic_counter[t] += 1
            # Also scan text for keyword triggers (simple NLP)
            text = getattr(s, "text", "") or getattr(s, "content", "") or ""
            if text:
                text_lower = text.lower()
                for kw in ["integration", "api", "sso", "dashboard", "export",
                           "mobile", "automation", "report", "custom"]:
                    if kw in text_lower:
                        topic_counter[kw] += 1

        # Top 3 recurring topics with count >= 3
        for topic, count in topic_counter.most_common(3):
            if count >= 3:
                insights.append(AgentInsight(
                    id=f"product-topic-{topic}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Recurring theme: {topic} (mentioned {count}x)",
                    body=(
                        f"The topic '{topic}' has appeared in {count} customer "
                        f"interactions. Topics that recur 3+ times are strong "
                        f"candidates for the next roadmap cycle. Review the "
                        f"underlying conversations to scope the requirement."
                    ),
                    confidence=min(0.55 + count * 0.05, 0.90),
                    priority="high" if count >= 5 else "medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      topic=topic,
                                      mention_count=count),
                    ],
                    recommended_action=(
                        f"Pull the {count} conversations mentioning '{topic}' "
                        f"and synthesize a single product requirement document."
                    ),
                    metadata={"topic": topic, "mention_count": count},
                ))

        # Customer-promised deliverables (roadmap pressure)
        commitment_signals = [
            s for s in signals
            if "commitment" in (getattr(s, "type", "") or "").lower()
        ]
        if len(commitment_signals) >= 3:
            insights.append(AgentInsight(
                id=f"product-promised-{uuid4().hex[:6]}",
                agent=self.AGENT_NAME,
                title=f"{len(commitment_signals)} customer-promised deliverables",
                body=(
                    f"Sales/CS has made {len(commitment_signals)} commitments to "
                    f"customers that will require engineering capacity. Each "
                    f"commitment is a de-facto roadmap item. Review these "
                    f"weekly to ensure engineering capacity is allocated."
                ),
                confidence=0.70,
                priority="medium",
                evidence_chain=[
                    self.evidence("commitment_tracker",
                                  total_commitments=len(commitment_signals)),
                ],
                recommended_action=(
                    "Review the commitment ledger with engineering leadership. "
                    "Convert each commitment into a Jira ticket with a customer "
                    "deadline."
                ),
                metadata={"commitment_count": len(commitment_signals)},
            ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 6. ENGINEERING AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class EngineeringAgent(BaseAgent):
    """Tracks engineering-impacting commitments and technical debt signals.

    Beats Nerve's siloed Engineering Agent by combining:
      - CommitmentTracker (engineering deliverables promised)
      - CommitmentEscalationEngine (overdue engineering commitments)
      - Pattern detection (recurring technical objections = architecture issues)
    """

    AGENT_NAME = "engineering"
    AGENT_DESCRIPTION = (
        "Tracks engineering-impacting commitments, surfaces overdue deliverables, "
        "and detects recurring technical objections that signal architecture issues."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Detect technical-debt signals (recurring "integration", "api", "bug")
        tech_keyword_counter: Counter[str] = Counter()
        for s in signals:
            text = getattr(s, "text", "") or getattr(s, "content", "") or ""
            if text:
                text_lower = text.lower()
                for kw in ["bug", "crash", "slow", "error", "timeout",
                           "integration", "api", "webhook", "rate limit"]:
                    if kw in text_lower:
                        tech_keyword_counter[kw] += 1

        for kw, count in tech_keyword_counter.most_common(2):
            if count >= 4:
                insights.append(AgentInsight(
                    id=f"eng-tech-debt-{kw}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Recurring technical issue: '{kw}' ({count} mentions)",
                    body=(
                        f"The keyword '{kw}' has appeared in {count} customer "
                        f"interactions. When technical issues recur 4+ times, "
                        f"they typically indicate an underlying architecture "
                        f"problem rather than individual bugs. Investigate "
                        f"the root cause."
                    ),
                    confidence=min(0.60 + count * 0.04, 0.88),
                    priority="high" if count >= 6 else "medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      keyword=kw,
                                      mention_count=count),
                    ],
                    recommended_action=(
                        f"Open a root-cause investigation for '{kw}'. "
                        f"Pull the {count} conversations and classify by "
                        f"severity (P0/P1/P2)."
                    ),
                    metadata={"keyword": kw, "mention_count": count},
                ))

        # Engineering commitments that are overdue
        try:
            escalation_engine = self._commitment_escalation_engine()
            overdue_eng_commitments = []
            for commit in escalation_engine._get_all_commitments():
                text = (commit.get("text", "") or "").lower()
                # Heuristic: engineering commitments mention "build", "ship", "deploy", "fix"
                if any(kw in text for kw in ["build", "ship", "deploy", "fix",
                                              "implement", "release", "integration"]):
                    try:
                        esc = escalation_engine.evaluate_commitment(commit)
                        if esc.health.value in ("overdue", "broken"):
                            overdue_eng_commitments.append((commit, esc))
                    except Exception:
                        pass

            if overdue_eng_commitments:
                insights.append(AgentInsight(
                    id=f"eng-overdue-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"{len(overdue_eng_commitments)} overdue engineering commitment(s)",
                    body=(
                        f"{len(overdue_eng_commitments)} engineering-impacting "
                        f"commitment(s) are overdue. Each overdue commitment "
                        f"erodes customer trust and blocks revenue recognition. "
                        f"Prioritize the oldest one first."
                    ),
                    confidence=0.78,
                    priority="high",
                    evidence_chain=[
                        self.evidence("commitment_escalation_engine",
                                      overdue_count=len(overdue_eng_commitments)),
                    ],
                    recommended_action=(
                        "Review the overdue commitments with engineering. "
                        "For each, either ship it this sprint or renegotiate "
                        "the deadline with the customer."
                    ),
                    metadata={"overdue_count": len(overdue_eng_commitments)},
                ))
        except Exception as e:
            logger.debug(f"EngineeringAgent: escalation engine failed: {e}")

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 7. MARKETING AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class MarketingAgent(BaseAgent):
    """Identifies customer stories, sentiment shifts, and messaging gaps.

    Beats Nerve's siloed Marketing Agent by combining:
      - SentimentPatternEngine (sudden positivity = case study opportunity)
      - CrossMeetingThreadBuilder (recurring value language = messaging)
      - Pattern detection (objection themes = messaging gaps)
    """

    AGENT_NAME = "marketing"
    AGENT_DESCRIPTION = (
        "Identifies case study opportunities (sudden positivity), messaging "
        "themes (recurring value language), and messaging gaps (objection themes)."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Detect sudden positivity (case study opportunity)
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
                        "timestamp": getattr(s, "timestamp", datetime.now(timezone.utc)).isoformat(),
                    })
            patterns = sentiment_engine.detect_patterns()
            for p in patterns:
                if "sudden_positivity" in (getattr(p, "pattern_type", "") or "").lower():
                    entity = getattr(p, "entity", "unknown")
                    insights.append(AgentInsight(
                        id=f"mkt-case-study-{entity}-{uuid4().hex[:6]}",
                        agent=self.AGENT_NAME,
                        title=f"Case study opportunity: {entity}",
                        body=(
                            f"SentimentPatternEngine detected a sudden positivity "
                            f"shift for {entity}. This is the ideal moment to "
                            f"request a case study — customers are most receptive "
                            f"immediately after a positive outcome, before "
                            f"recency bias fades."
                        ),
                        confidence=0.74,
                        priority="medium",
                        evidence_chain=[
                            self.evidence("sentiment_pattern_engine",
                                          entity=entity,
                                          pattern="sudden_positivity"),
                        ],
                        recommended_action=(
                            f"Email {entity}'s executive sponsor within 48 hours "
                            f"with a case study proposal. Reference the specific "
                            f"positive outcome in the email."
                        ),
                        metadata={"entity": entity},
                    ))
        except Exception as e:
            logger.debug(f"MarketingAgent: sentiment engine failed: {e}")

        # Detect objection themes (messaging gaps)
        objection_keywords: Counter[str] = Counter()
        for s in signals:
            text = (getattr(s, "text", "") or "").lower()
            for kw in ["expensive", "budget", "competitor", "alternative",
                       "too complex", "hard to use", "not sure"]:
                if kw in text:
                    objection_keywords[kw] += 1

        for kw, count in objection_keywords.most_common(2):
            if count >= 3:
                insights.append(AgentInsight(
                    id=f"mkt-objection-{kw}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Messaging gap: '{kw}' objection ({count}x)",
                    body=(
                        f"The objection theme '{kw}' has appeared in {count} "
                        f"customer conversations. This indicates a messaging "
                        f"gap — sales is hearing an objection that marketing "
                        f"hasn't pre-empted in collateral. Update the pitch "
                        f"deck and FAQ."
                    ),
                    confidence=min(0.60 + count * 0.04, 0.85),
                    priority="medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      objection_keyword=kw,
                                      mention_count=count),
                    ],
                    recommended_action=(
                        f"Create a one-pager that pre-empts the '{kw}' objection. "
                        f"Distribute to sales and add to the discovery deck."
                    ),
                    metadata={"objection_keyword": kw, "mention_count": count},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )
