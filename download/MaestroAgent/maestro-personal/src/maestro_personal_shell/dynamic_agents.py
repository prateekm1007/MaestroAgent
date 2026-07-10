"""
Dynamic agent activation + commitment simulation + materiality gate 2.0.

CEO Directive 4 (Days 22-30): Reasoning & Agent Upgrades.

1. DYNAMIC AGENT ACTIVATION
   Instead of running all 8 agents on every situation, dynamically select
   only the agents relevant to the situation's content. This reduces
   latency and improves precision (irrelevant agents produce noise).

2. COMMITMENT SIMULATION
   "If I take on this new commitment, what conflicts with my existing
   commitments?" — analyzes deadline overlaps, entity overload, and
   priority conflicts before the user makes a promise.

3. MATERIALITY GATE 2.0
   Learns from user dismissals (behavior patterns from learning_loop_v2).
   If the user dismisses 80% of low-urgency suggestions, the gate
   raises the threshold for low-urgency items.
"""

from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Agent relevance keywords — each agent is relevant when these appear
AGENT_RELEVANCE: dict[str, list[str]] = {
    "sales": ["contract", "deal", "pricing", "proposal", "renewal", "negotiat",
              "discount", "revenue", "quota", "pipeline", "close", "win"],
    "customer_success": ["renewal", "churn", "satisfaction", "escalation",
                         "onboarding", "training", "support", "feedback",
                         "relationship", "account", "retention"],
    "finance": ["invoice", "payment", "budget", "cost", "revenue", "spend",
                "forecast", "pricing", "margin", "p&l", "billing"],
    "engineering": ["deploy", "code", "api", "bug", "feature", "infra",
                    "migration", "architecture", "technical", "sprint",
                    "release", "build", "test"],
    "product": ["roadmap", "feature", "requirement", "spec", "user story",
                "priority", "backlog", "design", "ux", "release"],
    "strategy": ["strategy", "vision", "roadmap", "priority", "goal",
                 "objective", "okr", "kpi", "direction", "market"],
    "communications": ["email", "announce", "notify", "message",
                       "draft", "respond", "follow up", "reply",
                       "communicate", "stakeholder"],
    "chief_of_staff": [],  # always relevant — broad prioritization
}


def select_relevant_agents(
    situation_text: str,
    signals: list[Any] | None = None,
    max_agents: int = 3,
) -> list[str]:
    """Dynamically select which agents are relevant to this situation.

    Instead of running all 8 agents on every situation, this function
    analyzes the situation's content and selects only the agents that
    have relevant expertise.

    Args:
        situation_text: The situation/commitment text
        signals: Related signals for additional context
        max_agents: Maximum agents to activate (default 3)

    Returns: List of agent names to activate
    """
    text_lower = situation_text.lower()

    # Build a combined text blob from situation + signals
    combined = text_lower
    if signals:
        for sig in signals[:5]:
            sig_text = str(getattr(sig, "text", "") or (sig.get("text", "") if isinstance(sig, dict) else ""))
            combined += " " + sig_text.lower()

    # Score each agent by keyword matches
    scores: dict[str, int] = {}
    for agent, keywords in AGENT_RELEVANCE.items():
        if not keywords:
            # chief_of_staff is always relevant
            scores[agent] = 1
            continue
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[agent] = score

    # Sort by score (descending), take top N
    sorted_agents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    selected = [agent for agent, score in sorted_agents[:max_agents] if score > 0]

    # Always include chief_of_staff if not already selected (broad prioritizer)
    if "chief_of_staff" not in selected and len(selected) < max_agents:
        selected.append("chief_of_staff")

    # If nothing matched, default to chief_of_staff + customer_success
    if not selected:
        selected = ["chief_of_staff", "customer_success"]

    return selected[:max_agents]


def simulate_commitment_impact(
    new_commitment_text: str,
    new_entity: str,
    new_deadline: str | None,
    existing_commitments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Simulate the impact of taking on a new commitment.

    "If I take this on, what conflicts with my existing commitments?"

    Analyzes:
    1. Deadline overlaps — does the new deadline conflict with others?
    2. Entity overload — too many commitments for the same entity?
    3. Topic conflicts — same topic with different deadlines?
    4. Priority dilution — too many active commitments overall?

    Returns:
    {
        "risk_level": "low" | "medium" | "high",
        "conflicts": [list of conflict descriptions],
        "recommendation": "proceed" | "negotiate deadline" | "decline",
        "active_commitment_count": N,
        "entity_commitment_count": N,
    }
    """
    conflicts = []
    risk_score = 0

    # Count active commitments
    active_count = len(existing_commitments)
    if active_count > 10:
        conflicts.append(f"High commitment load: {active_count} active commitments")
        risk_score += 2
    elif active_count > 5:
        conflicts.append(f"Moderate commitment load: {active_count} active commitments")
        risk_score += 1

    # Count commitments for the same entity
    entity_commitments = [
        c for c in existing_commitments
        if str(c.get("entity", "")).lower() == new_entity.lower()
    ]
    entity_count = len(entity_commitments)
    if entity_count > 3:
        conflicts.append(
            f"Entity overload: {entity_count} active commitments for {new_entity}. "
            f"Adding another may dilute attention."
        )
        risk_score += 2
    elif entity_count > 1:
        conflicts.append(f"{entity_count} existing commitments for {new_entity}")
        risk_score += 1

    # Check for deadline conflicts
    if new_deadline:
        for c in existing_commitments:
            c_deadline = c.get("deadline", "") or (c.get("metadata", {}).get("deadline_text", ""))
            if c_deadline and new_deadline and c_deadline == new_deadline:
                conflicts.append(
                    f"Deadline conflict: another commitment due '{new_deadline}' — "
                    f"'{str(c.get('text', ''))[:60]}'"
                )
                risk_score += 2

    # Check for topic overlap (same keywords in multiple commitments)
    new_words = set(new_commitment_text.lower().split())
    common_words = {"i", "will", "the", "to", "a", "an", "by", "for", "send", "sent"}
    new_keywords = new_words - common_words

    for c in existing_commitments:
        c_text = str(c.get("text", "")).lower()
        c_words = set(c_text.split()) - common_words
        overlap = new_keywords & c_words
        if len(overlap) >= 2:
            conflicts.append(
                f"Topic overlap with: '{c_text[:60]}' "
                f"(shared: {', '.join(list(overlap)[:3])})"
            )
            risk_score += 1

    # Determine risk level
    if risk_score >= 4:
        risk_level = "high"
        recommendation = "decline"
    elif risk_score >= 2:
        risk_level = "medium"
        recommendation = "negotiate deadline"
    else:
        risk_level = "low"
        recommendation = "proceed"

    return {
        "risk_level": risk_level,
        "conflicts": conflicts[:5],  # max 5 conflicts
        "recommendation": recommendation,
        "active_commitment_count": active_count,
        "entity_commitment_count": entity_count,
        "risk_score": risk_score,
    }


async def materiality_gate_v2(
    commitment: dict[str, Any],
    context: dict[str, Any] | None = None,
    user_email: str = "bootstrap",
) -> dict[str, Any]:
    """Materiality Gate 2.0 — learns from user dismissal patterns.

    Directive 4: the materiality gate now uses user behavior patterns
    to adjust its thresholds. If the user dismisses 80% of low-urgency
    suggestions, the gate raises the bar for low-urgency items.

    Falls back to the original materiality gate when no behavior data.
    """
    from maestro_personal_shell.materiality_gate import _rule_based_materiality, evaluate_materiality

    # Get user behavior patterns
    behavior = {}
    try:
        from maestro_personal_shell.learning_loop_v2 import get_behavior_patterns
        behavior = get_behavior_patterns(user_email=user_email)
    except Exception as e:
        logger.debug("Behavior patterns fetch failed: %s", e)

    # Get the base materiality assessment
    base_result = await evaluate_materiality(commitment, context)

    # Adjust based on behavior patterns
    dismissal_rate = behavior.get("dismissal_rate", 0)
    total_behaviors = behavior.get("total_behaviors", 0)

    if total_behaviors >= 5 and dismissal_rate > 0.5:
        # User dismisses >50% of suggestions — be more selective
        urgency = base_result.get("urgency", "low")
        materiality_score = base_result.get("materiality_score", 0.5)

        # If this is low urgency and user dismisses most low-urgency items, suppress
        if urgency == "low" and dismissal_rate > 0.6:
            return {
                "should_speak": False,
                "materiality_score": materiality_score * 0.5,
                "urgency": "low",
                "reasoning": f"Suppressed: user dismisses {dismissal_rate:.0%} of suggestions "
                             f"(low-urgency items rarely retained)",
                "llm_powered": base_result.get("llm_powered", False),
                "behavior_adjusted": True,
            }

        # If medium urgency and user dismisses >70%, raise the bar
        if urgency == "medium" and dismissal_rate > 0.7:
            if materiality_score < 0.6:
                return {
                    "should_speak": False,
                    "materiality_score": materiality_score,
                    "urgency": "medium",
                    "reasoning": f"Suppressed: user dismisses {dismissal_rate:.0%} of suggestions "
                                 f"(medium-urgency below 0.6 threshold)",
                    "llm_powered": base_result.get("llm_powered", False),
                    "behavior_adjusted": True,
                }

    # Check if this agent is frequently dismissed
    most_dismissed_agent = behavior.get("most_dismissed_agent")
    if most_dismissed_agent:
        agent_rate = behavior.get("dismissal_rate_by_agent", {}).get(most_dismissed_agent, 0)
        if agent_rate > 0.8:
            # If the whisper comes from this agent, suppress
            agent_whispers = context.get("agent_whispers", []) if context else []
            for w in agent_whispers:
                if w.get("agent") == most_dismissed_agent and agent_rate > 0.8:
                    return {
                        "should_speak": False,
                        "materiality_score": base_result.get("materiality_score", 0.5),
                        "urgency": base_result.get("urgency", "low"),
                        "reasoning": f"Suppressed: '{most_dismissed_agent}' agent dismissed "
                                     f"{agent_rate:.0%} of the time",
                        "llm_powered": base_result.get("llm_powered", False),
                        "behavior_adjusted": True,
                    }

    # No behavior-based suppression — return base result
    return base_result
