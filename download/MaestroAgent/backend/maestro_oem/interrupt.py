"""Interrupt Intelligence — decide which events warrant interruption.

Not all interruptions are equal. Maestro decides:
  ignore → notify → recommend → escalate → interrupt

Exactly like human judgment.

The InterruptEngine takes a feed event and decides:
  - Should the user be interrupted right now?
  - What's the priority? (ignore, notify, recommend, escalate, interrupt)
  - What's the recommended delivery? (banner, toast, modal, push, silent)
  - When should it be delivered? (immediately, batched, deferred)

Decision factors:
  - Event severity (broken commitment > law strengthened)
  - Business impact (ARR at stake)
  - Confidence (high confidence = more urgent)
  - User's current cognitive load (don't interrupt overloaded users)
  - Time of day (don't interrupt at 2am unless critical)
  - User's current intent (don't interrupt a negotiation for a low-priority event)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ─── Interrupt priority levels ─────────────────────────────────────────────

IGNORE = "ignore"
NOTIFY = "notify"
RECOMMEND = "recommend"
ESCALATE = "escalate"
INTERRUPT = "interrupt"

PRIORITY_ORDER = [IGNORE, NOTIFY, RECOMMEND, ESCALATE, INTERRUPT]


class InterruptEngine:
    """Decides which events warrant interruption.

    Usage:
        engine = InterruptEngine(model, signals)
        decision = engine.evaluate(event, user_cognitive_load=35, user_intent="preparing_for_negotiation")
        # decision = {priority: "recommend", delivery: "toast", timing: "immediate"}
    """

    # Event type → base priority
    _EVENT_PRIORITY = {
        "commitment_broken": ESCALATE,
        "customer_churned": ESCALATE,
        "customer_drifting": RECOMMEND,
        "expert_overloaded": RECOMMEND,
        "concentration_risk": RECOMMEND,
        "law_invalidated": RECOMMEND,
        "law_challenged": NOTIFY,
        "law_strengthened": IGNORE,  # Good news, don't interrupt
        "customer_renewed": IGNORE,  # Good news
        "prediction_resolved": NOTIFY,
    }

    # Delivery method per priority
    _DELIVERY = {
        IGNORE: "silent",
        NOTIFY: "badge",
        RECOMMEND: "toast",
        ESCALATE: "banner",
        INTERRUPT: "modal",
    }

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def evaluate(
        self,
        event: dict[str, Any],
        user_cognitive_load: float = 0,
        user_intent: str = "",
        user_email: str = "",
    ) -> dict[str, Any]:
        """Evaluate whether an event should interrupt the user.

        Args:
            event: A feed event dict (from ExecutiveFeed)
            user_cognitive_load: 0-100 (higher = more loaded)
            user_intent: The user's current inferred intent
            user_email: The user's email

        Returns:
            - priority: ignore | notify | recommend | escalate | interrupt
            - delivery: silent | badge | toast | banner | modal
            - timing: immediate | batched | deferred
            - reason: why this priority was chosen
            - suppression_reason: why it was suppressed (if ignored)
        """
        event_type = event.get("event_type", "")
        confidence = event.get("confidence", 0.5)
        business_impact = event.get("business_impact", "")
        now = datetime.now(timezone.utc)
        hour = now.hour

        # Start with the base priority for this event type
        base_priority = self._EVENT_PRIORITY.get(event_type, NOTIFY)
        priority_idx = PRIORITY_ORDER.index(base_priority)

        # ─── Adjust up for severity ────────────────────────────────────────
        # High ARR at stake → escalate
        arr_in_impact = self._extract_arr(business_impact)
        if arr_in_impact > 2_000_000:
            priority_idx = min(4, priority_idx + 1)
        if arr_in_impact > 5_000_000:
            priority_idx = min(4, priority_idx + 1)

        # High confidence → slight boost
        if confidence > 0.9:
            priority_idx = min(4, priority_idx + 0)  # No boost, just don't suppress

        # ─── Adjust down for user state ────────────────────────────────────
        # Don't interrupt overloaded users unless it's critical
        if user_cognitive_load > 70 and priority_idx < 3:
            priority_idx = max(0, priority_idx - 1)

        # Don't interrupt during a negotiation unless it's escalate+
        if user_intent == "preparing_for_negotiation" and priority_idx < 3:
            priority_idx = max(0, priority_idx - 1)

        # Don't interrupt during incident resolution unless it's about the incident
        if user_intent == "resolving_incident" and "incident" not in event_type:
            priority_idx = max(0, priority_idx - 1)

        # ─── Time-of-day adjustments ───────────────────────────────────────
        # Late night: only interrupt for critical events
        if (hour < 7 or hour > 22) and priority_idx < 3:
            priority_idx = 0  # Suppress to ignore

        # ─── Good news suppression ─────────────────────────────────────────
        # Don't interrupt for good news (law strengthened, customer renewed)
        if event_type in ("law_strengthened", "customer_renewed") and priority_idx > 1:
            priority_idx = 1  # Cap at notify

        priority = PRIORITY_ORDER[max(0, min(4, int(priority_idx)))]
        delivery = self._DELIVERY[priority]

        # Timing
        if priority in (INTERRUPT, ESCALATE):
            timing = "immediate"
        elif priority == RECOMMEND:
            timing = "immediate"
        elif priority == NOTIFY:
            timing = "batched"
        else:
            timing = "deferred"

        reason = self._explain(priority, event_type, user_cognitive_load, user_intent, arr_in_impact)
        suppression = self._suppression_reason(priority, event_type, user_cognitive_load, hour, user_intent)

        return {
            "priority": priority,
            "delivery": delivery,
            "timing": timing,
            "reason": reason,
            "suppression_reason": suppression,
            "event_type": event_type,
            "arr_at_stake": arr_in_impact,
            "user_cognitive_load": user_cognitive_load,
            "user_intent": user_intent,
        }

    def evaluate_feed(
        self,
        events: list[dict[str, Any]],
        user_cognitive_load: float = 0,
        user_intent: str = "",
        user_email: str = "",
    ) -> list[dict[str, Any]]:
        """Evaluate a full feed and return only the events that warrant attention.

        Events with priority 'ignore' are filtered out.
        """
        evaluated = []
        for event in events:
            decision = self.evaluate(event, user_cognitive_load, user_intent, user_email)
            if decision["priority"] != IGNORE:
                evaluated.append({
                    **event,
                    "interrupt_decision": decision,
                })
        return evaluated

    def _extract_arr(self, business_impact: str) -> float:
        """Extract ARR value from a business impact string like '$3,200,000 ARR at stake.'"""
        import re
        match = re.search(r'\$([\d,]+)', business_impact)
        if match:
            return float(match.group(1).replace(',', ''))
        return 0.0

    def _explain(self, priority, event_type, cognitive_load, intent, arr) -> str:
        parts = [f"Priority: {priority}"]
        parts.append(f"Event type: {event_type}")
        if arr > 0:
            parts.append(f"ARR at stake: ${arr:,.0f}")
        if cognitive_load > 70:
            parts.append(f"User cognitive load is high ({cognitive_load:.0f}) — suppressed")
        if intent:
            parts.append(f"User intent: {intent}")
        return ". ".join(parts) + "."

    def _suppression_reason(self, priority, event_type, cognitive_load, hour, intent) -> str:
        if priority == IGNORE:
            if hour < 7 or hour > 22:
                return "Suppressed: outside business hours"
            if cognitive_load > 70:
                return "Suppressed: user cognitive load is high"
            if event_type in ("law_strengthened", "customer_renewed"):
                return "Suppressed: good news, no interruption needed"
            return "Suppressed: low priority"
        return ""
