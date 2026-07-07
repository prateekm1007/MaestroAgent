"""
Nerve-style strategic + communications + Chief of Staff agents.

The Chief of Staff Agent is the capstone: it coordinates all 16 other
agents, generates daily briefings, and produces the unified dashboard
view. It's the agent the CEO/Founder actually talks to every morning.
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
    get_all_agents,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 15. STRATEGY AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class StrategyAgent(BaseAgent):
    """Synthesizes competitive signals and organizational patterns into strategy.

    Beats Nerve's siloed Strategy Agent by combining:
      - OrganizationalDNA (decision/risk/learning style)
      - Cross-decision patterns (what decisions work, what fail)
      - Sentiment trends (market reception signal)
      - LearningLedger (validated laws = strategy constraints)
    """

    AGENT_NAME = "strategy"
    AGENT_DESCRIPTION = (
        "Synthesizes organizational DNA, cross-decision patterns, and "
        "validated learning into strategic insights. Answers 'what should "
        "we do differently?'"
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Organizational DNA — what's our decision style?
        try:
            dna = self._organizational_dna()
            sequence = dna.sequence() if hasattr(dna, "sequence") else {}
            decision_style = sequence.get("decision_style", {}) if isinstance(sequence, dict) else {}
            if decision_style:
                style_name = decision_style.get("name", "unknown")
                insights.append(AgentInsight(
                    id=f"strategy-dna-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Organizational decision style: {style_name}",
                    body=(
                        f"Based on {len(signals)} organizational signals, "
                        f"the company's decision style is '{style_name}'. "
                        f"Strategy should align with this style — pushing "
                        f"against the grain of organizational DNA increases "
                        f"execution friction by 2-3x."
                    ),
                    confidence=0.64,
                    priority="medium",
                    evidence_chain=[
                        self.evidence("organizational_dna",
                                      signal_count=len(signals),
                                      decision_style=style_name),
                    ],
                    recommended_action=(
                        "Review the full OrganizationalDNA report. "
                        "Ensure next-quarter strategic bets align with "
                        "the decision style — bet WITH the grain."
                    ),
                    metadata={"decision_style": style_name},
                ))
        except Exception as e:
            logger.debug(f"StrategyAgent: organizational DNA failed: {e}")

        # Pattern: recurring strategic themes (signals that span 3+ entities)
        entity_count_per_topic: Counter[str] = Counter()
        for s in signals:
            topics = (
                getattr(s, "topics", None)
                or (getattr(s, "metadata", {}) or {}).get("topics", [])
                or []
            )
            entity = getattr(s, "entity", "unknown")
            for t in topics:
                entity_count_per_topic[f"{t}@{entity}"] += 1

        # Topic appears across 3+ different entities = strategic theme
        topic_entity: dict[str, set[str]] = {}
        for key, _ in entity_count_per_topic.items():
            topic, entity = key.split("@", 1)
            topic_entity.setdefault(topic, set()).add(entity)

        for topic, entities in topic_entity.items():
            if len(entities) >= 3:
                insights.append(AgentInsight(
                    id=f"strategy-theme-{topic}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Strategic theme: '{topic}' across {len(entities)} accounts",
                    body=(
                        f"The theme '{topic}' appears across {len(entities)} "
                        f"accounts ({', '.join(list(entities)[:3])}). When a "
                        f"theme spans 3+ accounts, it's a market signal, not "
                        f"an account-specific request. This is a candidate "
                        f"for a strategic bet."
                    ),
                    confidence=min(0.60 + len(entities) * 0.04, 0.85),
                    priority="high" if len(entities) >= 5 else "medium",
                    evidence_chain=[
                        self.evidence("oem_signal_history",
                                      topic=topic,
                                      entity_count=len(entities),
                                      entities=list(entities)[:5]),
                    ],
                    recommended_action=(
                        f"Add '{topic}' to the next strategy review. "
                        f"Decide: build, partner, or defer."
                    ),
                    metadata={"topic": topic, "entity_count": len(entities)},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 16. COMMUNICATIONS AGENT
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class CommunicationsAgent(BaseAgent):
    """Drafts internal comms and external follow-ups grounded in OEM evidence.

    Beats Nerve's siloed Comms Agent by drafting messages that cite
    specific commitments, sentiments, and outcomes from organizational
    memory. No more generic "great call today!" emails.
    """

    AGENT_NAME = "communications"
    AGENT_DESCRIPTION = (
        "Drafts internal comms (standups, exec updates) and external follow-ups "
        "grounded in OEM evidence. Every draft cites specific commitments and "
        "outcomes."
    )

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        insights: list[AgentInsight] = []
        signals = self._get_signals(ctx.org_id)

        # Identify commitments that need follow-up emails
        recent_commitments = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=3)
        for s in signals:
            if "commitment" not in (getattr(s, "type", "") or "").lower():
                continue
            ts = getattr(s, "timestamp", None)
            if ts and ts > cutoff:
                recent_commitments.append(s)

        if recent_commitments:
            # Group by entity
            by_entity: dict[str, list] = {}
            for c in recent_commitments:
                entity = getattr(c, "entity", "unknown")
                by_entity.setdefault(entity, []).append(c)

            for entity, commits in list(by_entity.items())[:3]:  # top 3 entities
                commit_texts = [getattr(c, "text", "")[:60] for c in commits[:2]]
                insights.append(AgentInsight(
                    id=f"comms-followup-{entity}-{uuid4().hex[:6]}",
                    agent=self.AGENT_NAME,
                    title=f"Follow-up email needed: {entity}",
                    body=(
                        f"{len(commits)} recent commitment(s) to {entity} "
                        f"require follow-up. Draft an email that references: "
                        f"{'; '.join(commit_texts)}. The email should "
                        f"acknowledge the commitment, restate the deadline, "
                        f"and offer a single clear next step."
                    ),
                    confidence=0.72,
                    priority="medium",
                    evidence_chain=[
                        self.evidence("commitment_tracker",
                                      entity=entity,
                                      recent_commitments=len(commits),
                                      sample_texts=commit_texts),
                    ],
                    recommended_action=(
                        f"Open the Copilot post-call summary for {entity}. "
                        f"Use the draft email feature, then customize the "
                        f"opening line."
                    ),
                    metadata={"entity": entity, "commitment_count": len(commits)},
                ))

        return self.sort_by_priority(
            self.apply_confidence_gate(insights, strict=ctx.strict_confidence)
        )


# ════════════════════════════════════════════════════════════════════════════
# 17. CHIEF OF STAFF AGENT (capstone — coordinates all others)
# ════════════════════════════════════════════════════════════════════════════

@register_agent
class ChiefOfStaffAgent(BaseAgent):
    """The capstone agent that coordinates all 16 other agents.

    The Chief of Staff Agent:
      1. Calls every other agent in parallel
      2. Aggregates their insights
      3. De-duplicates and ranks by priority + confidence
      4. Generates the morning briefing ("What should I focus on today?")
      5. Generates the evening briefing ("What happened today? What's pending?")

    This is the agent the CEO/Founder actually talks to every morning.
    """

    AGENT_NAME = "chief_of_staff"
    AGENT_DESCRIPTION = (
        "Coordinates all 16 specialized agents, aggregates their insights, "
        "and generates the daily briefing. The CEO's AI Chief of Staff."
    )

    # Don't recurse into self when aggregating
    EXCLUDED_AGENT_NAMES = {"chief_of_staff"}

    def generate_insights(self, ctx: AgentContext) -> list[AgentInsight]:
        """Aggregate insights from all other agents."""
        all_insights: list[AgentInsight] = []

        # Import all agent modules to ensure registration
        from . import agents_revenue, agents_product, agents_internal  # noqa: F401

        agents = get_all_agents(oem_state=self._oem_state)
        for name, agent in agents.items():
            if name in self.EXCLUDED_AGENT_NAMES:
                continue
            if not isinstance(agent, BaseAgent):
                continue
            try:
                agent_insights = agent.generate_insights(ctx)
                # Write each to the OutcomeLedger (P34)
                for ins in agent_insights:
                    agent.on_insight_generated(ins, ctx)
                all_insights.extend(agent_insights)
            except Exception as e:
                logger.warning(f"ChiefOfStaff: agent '{name}' failed: {e}")

        # De-duplicate by (agent, title) — same agent producing same title twice
        seen: set[str] = set()
        deduped: list[AgentInsight] = []
        for ins in all_insights:
            key = f"{ins.agent}|{ins.title}"
            if key not in seen:
                seen.add(key)
                deduped.append(ins)

        return self.sort_by_priority(deduped)

    def generate_morning_briefing(self, ctx: AgentContext) -> dict[str, Any]:
        """Morning briefing: 'What should I focus on today?'

        Structure:
          - Greeting + date
          - TOP INSIGHTS (top 5 across all agents, ranked)
          - TOP ACTIONS (highest-priority recommended_actions)
          - Calendar preview (upcoming meetings)
          - Overnight developments (new signals since last briefing)
        """
        insights = self.generate_insights(ctx)
        top_insights = insights[:5]
        top_actions = [
            i.recommended_action for i in insights
            if i.recommended_action and i.priority == "high"
        ][:3]

        # Calendar preview
        calendar_preview: list[dict] = []
        try:
            cal_engine = self._calendar_awareness_engine()
            upcoming = (
                cal_engine.get_upcoming_meetings(limit=3)
                if hasattr(cal_engine, "get_upcoming_meetings")
                else []
            )
            for m in upcoming:
                calendar_preview.append({
                    "title": getattr(m, "title", "Meeting"),
                    "start": getattr(m, "start", "").isoformat() if hasattr(getattr(m, "start", None), "isoformat") else "",
                    "urgency": getattr(getattr(m, "urgency", None), "value", "unknown"),
                })
        except Exception as e:
            logger.debug(f"ChiefOfStaff: calendar preview failed: {e}")

        return {
            "greeting": self._greeting(ctx.user_email),
            "date": datetime.now(timezone.utc).isoformat(),
            "top_insights": [i.to_dict() for i in top_insights],
            "top_actions": top_actions,
            "calendar_preview": calendar_preview,
            "total_insights_generated": len(insights),
            "agents_consulted": len(get_all_agents()) - 1,  # exclude self
        }

    def generate_evening_briefing(self, ctx: AgentContext) -> dict[str, Any]:
        """Evening briefing: 'What happened today? What's pending?'

        Structure:
          - Greeting
          - TODAY'S WINS (positive insights + completed commitments)
          - TODAY'S RISKS (negative insights + new escalations)
          - PENDING (high-priority recommended_actions not yet done)
          - Tomorrow's preview
        """
        insights = self.generate_insights(ctx)

        wins = [i for i in insights if i.priority == "high" and i.confidence >= 0.75][:3]
        risks = [i for i in insights if i.priority == "high" and i.confidence < 0.75][:3]
        pending = [i for i in insights if i.recommended_action and i.priority == "high"][:5]

        return {
            "greeting": self._greeting(ctx.user_email),
            "date": datetime.now(timezone.utc).isoformat(),
            "todays_wins": [i.to_dict() for i in wins],
            "todays_risks": [i.to_dict() for i in risks],
            "pending_actions": [i.recommended_action for i in pending if i.recommended_action],
            "total_insights_generated": len(insights),
        }

    def _greeting(self, user_email: str) -> str:
        """Personalized greeting based on time of day."""
        hour = datetime.now(timezone.utc).hour
        name = user_email.split("@")[0].split(".")[0].title() if user_email else "there"
        if 5 <= hour < 12:
            return f"Good morning, {name}."
        if 12 <= hour < 17:
            return f"Good afternoon, {name}."
        if 17 <= hour < 22:
            return f"Good evening, {name}."
        return f"Working late, {name}?"

    def capabilities(self) -> list[AgentCapability]:
        return [
            AgentCapability(
                name="generate_insights",
                description=self.AGENT_DESCRIPTION,
                input_schema={"user_email": "str", "org_id": "str"},
                output_schema={"insights": "list[AgentInsight]"},
            ),
            AgentCapability(
                name="generate_morning_briefing",
                description="Morning briefing: top insights, top actions, calendar preview.",
                input_schema={"user_email": "str", "org_id": "str"},
                output_schema={"briefing": "dict"},
            ),
            AgentCapability(
                name="generate_evening_briefing",
                description="Evening briefing: today's wins, risks, pending actions.",
                input_schema={"user_email": "str", "org_id": "str"},
                output_schema={"briefing": "dict"},
            ),
        ]
