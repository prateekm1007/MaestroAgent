"""
Personal adapter layer for Nerve agents.

Per CEO Phase 3+ directive: build personal-mode adapters for the
enterprise engines that Nerve agents depend on. Same pattern as
_apply_personal_preparation_triggers — post-process/adapt in the shell,
don't modify the agents.

The problem: agents call BaseAgent._commitment_escalation_engine() etc.
which return enterprise engines that check for SignalType.CUSTOMER_COMMITMENT_MADE
(an enum). Personal signals use "commitment_made" (a string). The engines
find 0 commitments → agents produce 0 insights.

The fix: PersonalAgentAdapter wraps each agent and monkey-patches its
engine factory methods to return personal-mode adapters that:
  1. Read PersonalSignal objects (duck-typed)
  2. Match on string signal types (not enum)
  3. Produce the data structures agents expect (CommitmentEscalation, etc.)

Usage:
    adapter = PersonalAgentAdapter(shell)
    adapter.adapt_agent(agent)  # patches the agent's engine factories
    insights = agent.generate_insights(ctx)  # now produces real insights
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from dataclasses import dataclass, field
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Personal adapter data structures (match enterprise shapes agents expect)
# ---------------------------------------------------------------------------


@dataclass
class PersonalCommitmentEscalation:
    """Matches the shape of enterprise CommitmentEscalation.

    The agents check: esc.level.value, esc.health.value, esc.days_overdue.
    """
    entity: str = ""
    text: str = ""
    level: Any = None  # EscalationLevel-like
    health: Any = None  # CommitmentHealth-like
    days_overdue: int = 0


class _Level:
    """Simulates EscalationLevel enum."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"

    def __init__(self, value: str = "none"):
        self.value = value


class _Health:
    """Simulates CommitmentHealth enum."""
    CRITICAL = "critical"
    AT_RISK = "at_risk"
    STABLE = "stable"
    UNKNOWN = "unknown"

    def __init__(self, value: str = "unknown"):
        self.value = value


# ---------------------------------------------------------------------------
# Personal CommitmentEscalationEngine adapter
# ---------------------------------------------------------------------------


class PersonalCommitmentEscalationAdapter:
    """Personal-mode adapter for CommitmentEscalationEngine.

    Reads PersonalSignal objects, finds commitments, evaluates escalation
    based on days since last follow-up. Produces PersonalCommitmentEscalation
    objects that match the shape agents expect.
    """

    def __init__(self, oem_state: Any = None):
        self.oem = oem_state

    def _get_all_commitments(self) -> list[dict]:
        """Get all open commitments from personal signals.

        Matches on signal types containing "commitment" (string, not enum).
        Returns dicts with: entity, text, signal_id, timestamp, days_old.
        """
        if not self.oem or not hasattr(self.oem, "signals"):
            return []

        commitments = []
        now = datetime.now(timezone.utc)

        for sig in self.oem.signals:
            sig_type = str(getattr(sig, "signal_type", "") or
                          getattr(getattr(sig, "type", ""), "value", "")).lower()

            if "commitment" in sig_type or "promise" in sig_type:
                ts = getattr(sig, "timestamp", now)
                if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                days_old = (now - ts).days if hasattr(ts, "year") else 0

                commitments.append({
                    "entity": getattr(sig, "entity", "unknown"),
                    "text": getattr(sig, "text", ""),
                    "signal_id": getattr(sig, "signal_id", str(id(sig))),
                    "timestamp": ts,
                    "days_old": days_old,
                })

        return commitments

    def evaluate_commitment(self, commit: dict) -> PersonalCommitmentEscalation:
        """Evaluate a commitment's escalation level.

        Based on days since the commitment was made + whether the user
        has RESPONDED to follow-ups. A follow-up FROM the other party
        that the user hasn't addressed means the commitment is MORE
        urgent, not less.
        """
        days_old = commit.get("days_old", 0)
        entity = commit.get("entity", "unknown")
        text = commit.get("text", "")

        # Check if there are UNANSWERED follow-up signals for this entity
        # A follow-up from the other party that the user hasn't resolved
        # means the commitment is escalating, not stable.
        has_unanswered_followup = False
        has_resolution = False
        if self.oem and hasattr(self.oem, "signals"):
            commit_ts = commit.get("timestamp", datetime.now(timezone.utc))
            for sig in self.oem.signals:
                sig_type = str(getattr(sig, "signal_type", "") or
                              getattr(getattr(sig, "type", ""), "value", "")).lower()
                sig_entity = str(getattr(sig, "entity", "")).lower()
                if sig_entity != entity.lower():
                    continue

                sig_ts = getattr(sig, "timestamp", None)
                if sig_ts and hasattr(sig_ts, "year") and sig_ts > commit_ts:
                    if "follow_up" in sig_type or "followup" in sig_type:
                        has_unanswered_followup = True  # someone asked, user hasn't resolved
                    if "observed_fact" in sig_type and "sent" in str(getattr(sig, "text", "")).lower():
                        has_resolution = True  # the commitment was fulfilled

        # Escalation logic — follow-ups INCREASE urgency, they don't decrease it
        if has_resolution:
            level = _Level("none")
            health = _Health("stable")
        elif days_old >= 14 or (days_old >= 7 and has_unanswered_followup):
            level = _Level("critical")
            health = _Health("critical")
        elif days_old >= 7 or (days_old >= 3 and has_unanswered_followup):
            level = _Level("high")
            health = _Health("at_risk")
        elif days_old >= 3:
            level = _Level("medium")
            health = _Health("at_risk")
        else:
            level = _Level("low")
            health = _Health("stable")

        return PersonalCommitmentEscalation(
            entity=entity,
            text=text,
            level=level,
            health=health,
            days_overdue=days_old,
        )


# ---------------------------------------------------------------------------
# Personal DealHealthEngine adapter
# ---------------------------------------------------------------------------


class PersonalDealHealthAdapter:
    """Personal-mode adapter for DealHealthEngine.

    In personal mode, "deal health" maps to "relationship health" — how
    healthy is the user's relationship with this entity based on signal
    patterns (commitments kept, follow-ups answered, meeting regularity).
    """

    def __init__(self, oem_state: Any = None):
        self.oem = oem_state

    def assess_entity(self, entity: str) -> dict:
        """Assess the health of a relationship with an entity."""
        if not self.oem or not hasattr(self.oem, "signals"):
            return {"status": "unknown", "score": 0.5, "risks": []}

        entity_signals = [
            s for s in self.oem.signals
            if str(getattr(s, "entity", "")).lower() == entity.lower()
        ]

        if not entity_signals:
            return {"status": "unknown", "score": 0.5, "risks": []}

        commitments = [s for s in entity_signals if "commitment" in str(getattr(s, "signal_type", "")).lower()]
        followups = [s for s in entity_signals if "follow_up" in str(getattr(s, "signal_type", "")).lower()]
        meetings = [s for s in entity_signals if "meeting" in str(getattr(s, "signal_type", "")).lower()]

        risks = []
        score = 0.7  # default healthy

        # Risk: commitments without follow-ups
        if commitments and not followups:
            risks.append(f"{len(commitments)} commitment(s) with no follow-up")
            score -= 0.2

        # Risk: follow-ups without new commitments (unanswered questions)
        if followups and len(followups) > len(commitments):
            risks.append(f"{len(followups)} unanswered follow-up(s)")
            score -= 0.15

        # Positive: regular meetings
        if meetings:
            score += 0.1

        score = max(0.0, min(1.0, score))
        status = "healthy" if score >= 0.6 else "at_risk" if score >= 0.3 else "critical"

        return {"status": status, "score": score, "risks": risks}


# ---------------------------------------------------------------------------
# PersonalAgentAdapter — patches agents to use personal adapters
# ---------------------------------------------------------------------------


class PersonalAgentAdapter:
    """Adapts Nerve agents to work with personal signals.

    Monkey-patches the agent's engine factory methods to return personal
    adapters instead of enterprise engines. Same pattern as
    _is_high_salience_signal wrapping in the shell.

    Usage:
        adapter = PersonalAgentAdapter(shell)
        for agent in nerve.agents.values():
            adapter.adapt_agent(agent)
    """

    def __init__(self, shell: Any) -> None:
        self._shell = shell
        self._oem_state = shell.oem_state
        self._escalation_adapter = PersonalCommitmentEscalationAdapter(oem_state=self._oem_state)
        self._deal_health_adapter = PersonalDealHealthAdapter(oem_state=self._oem_state)

    def adapt_agent(self, agent: Any) -> None:
        """Patch an agent's engine factories to use personal adapters."""
        # Patch _commitment_escalation_engine
        original_escalation = getattr(agent, "_commitment_escalation_engine", None)
        if original_escalation:
            agent._commitment_escalation_engine = lambda: self._escalation_adapter

        # Patch _deal_health_engine
        original_deal_health = getattr(agent, "_deal_health_engine", None)
        if original_deal_health:
            agent._deal_health_engine = lambda: self._deal_health_adapter

        # Patch _commitment_tracker to use personal signals
        original_tracker = getattr(agent, "_commitment_tracker", None)
        if original_tracker:
            agent._commitment_tracker = lambda: self._escalation_adapter

    def adapt_all(self, agents: dict[str, Any]) -> None:
        """Adapt all agents in a dict."""
        for agent in agents.values():
            self.adapt_agent(agent)
