"""Intent Engine — infer user intent from context, not events.

The core of ambient intelligence: the system knows what you're trying to
do without being told.

Old software reacts to events:
  "Email opened."

Maestro infers intent:
  "User is probably preparing for a negotiation."

The Intent Engine takes observable context signals:
  - Active application (email, calendar, GitHub, Jira, Slack, browser)
  - Time of day / day of week
  - Upcoming calendar events
  - Recent signal activity
  - Current OEM state (pending decisions, drift, risks)

And infers likely intents:
  - preparing_for_negotiation
  - reviewing_code
  - preparing_release
  - resolving_incident
  - board_update_preparation
  - approval_decision
  - customer_check_in
  - strategic_planning
  - daily_triage

Each inferred intent includes:
  - confidence (0-1)
  - why (what signals drove this inference)
  - what_maestro_knows (relevant OEM knowledge for this intent)
  - recommended_whisper (what to surface without being asked)

Privacy by design: the engine does NOT inspect content. It uses only
observable metadata (which app is active, calendar titles, recent signal
types) — never email bodies, document content, or keystrokes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


# ─── Intent taxonomy ───────────────────────────────────────────────────────

INTENTS = {
    "preparing_for_negotiation": {
        "label": "Preparing for a negotiation",
        "description": "User is likely preparing for a customer negotiation or renewal discussion.",
        "triggers": ["calendar_meeting_with_customer", "email_to_customer", "customer_drift_signal"],
    },
    "reviewing_code": {
        "label": "Reviewing code",
        "description": "User is likely reviewing a pull request or evaluating an engineering change.",
        "triggers": ["github_active", "pr_opened_recently", "engineering_law_relevant"],
    },
    "preparing_release": {
        "label": "Preparing a release",
        "description": "User is likely preparing to ship a release or deploy.",
        "triggers": ["github_active", "multiple_merges_recently", "release_pattern"],
    },
    "resolving_incident": {
        "label": "Resolving an incident",
        "description": "User is likely responding to an incident or P1.",
        "triggers": ["incident_recent", "p1_issue_created", "slack_escalation"],
    },
    "board_update_preparation": {
        "label": "Preparing a board update",
        "description": "User is likely preparing a board or executive update.",
        "triggers": ["calendar_board_meeting", "document_editing", "quarter_end_approaching"],
    },
    "approval_decision": {
        "label": "Making an approval decision",
        "description": "User is likely deciding whether to approve something.",
        "triggers": ["pending_approvals", "jira_transition_pending", "bottleneck_on_user"],
    },
    "customer_check_in": {
        "label": "Checking in on a customer",
        "description": "User is likely reviewing a customer relationship.",
        "triggers": ["crm_active", "customer_drift", "champion_quiet"],
    },
    "strategic_planning": {
        "label": "Strategic planning",
        "description": "User is likely doing strategic planning or roadmap work.",
        "triggers": ["calendar_planning_session", "rfc_created_recently", "quarter_end_approaching"],
    },
    "daily_triage": {
        "label": "Daily triage",
        "description": "User is likely doing their morning triage of pending items.",
        "triggers": ["morning_hours", "recommendations_pending", "inbox_check"],
    },
    "knowledge_hunting": {
        "label": "Searching for knowledge",
        "description": "User is likely looking for who knows what.",
        "triggers": ["question_asked_recently", "hidden_expert_relevant", "slack_question"],
    },
}


class IntentEngine:
    """Infers user intent from observable context.

    Usage:
        engine = IntentEngine(model, signals)
        intent = engine.infer(
            active_app="calendar",
            user="jane.d@example.com",
            calendar_context={"title": "Q4 renewal with <customer>", "participants": ["raj@example.com"]},
        )
        # intent = {intent: "preparing_for_negotiation", confidence: 0.85, ...}
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def infer(
        self,
        active_app: str = "",
        user: str = "",
        calendar_context: dict[str, Any] | None = None,
        url_context: str = "",
    ) -> dict[str, Any]:
        """Infer the user's likely intent from observable context.

        Args:
            active_app: "email" | "calendar" | "github" | "jira" | "slack" |
                        "browser" | "zoom" | "docs" | "crm"
            user: The user's email (for personalization)
            calendar_context: {title, participants, start_time, duration} if available
            url_context: The current URL (domain only, not full path)

        Returns:
            - intent: the inferred intent key
            - label: human-readable label
            - confidence: 0-1
            - why: what signals drove this inference
            - what_maestro_knows: relevant OEM knowledge
            - recommended_whisper: what to surface without being asked
            - alternative_intents: other possible intents with lower confidence

        Privacy: this function does NOT inspect content. It uses only:
          - which app is active (metadata)
          - calendar event titles (if the user opts in)
          - URL domain (not path)
          - recent signal types (from the OEM)
        No keystrokes, no document content, no email bodies.
        """
        calendar_context = calendar_context or {}
        now = datetime.now(timezone.utc)
        scores: dict[str, float] = {}
        reasons: dict[str, list[str]] = {}

        # ─── App-based inference ───────────────────────────────────────────
        if active_app == "calendar" or active_app == "zoom":
            cal_title = calendar_context.get("title", "").lower()
            participants = calendar_context.get("participants", [])

            # Customer meeting → negotiation prep
            external_participants = [p for p in participants if "@" in p and "acme" not in p.lower()]
            if external_participants or any(kw in cal_title for kw in ["renewal", "negotiation", "customer", "sales"]):
                scores["preparing_for_negotiation"] = scores.get("preparing_for_negotiation", 0) + 0.6
                reasons.setdefault("preparing_for_negotiation", []).append(
                    f"Calendar event '{calendar_context.get('title', '')}' has external participants"
                )

            # Board meeting → board update prep
            if any(kw in cal_title for kw in ["board", "investor", "quarterly", "qbr"]):
                scores["board_update_preparation"] = scores.get("board_update_preparation", 0) + 0.7
                reasons.setdefault("board_update_preparation", []).append(
                    f"Calendar event suggests board/executive meeting"
                )

            # Planning session → strategic planning
            if any(kw in cal_title for kw in ["planning", "roadmap", "strategy", "okr"]):
                scores["strategic_planning"] = scores.get("strategic_planning", 0) + 0.6
                reasons.setdefault("strategic_planning", []).append(
                    f"Calendar event suggests planning session"
                )

        if active_app == "github":
            scores["reviewing_code"] = scores.get("reviewing_code", 0) + 0.4
            reasons.setdefault("reviewing_code", []).append("GitHub is active")

            # Check for recent PR opens by this user
            from maestro_oem.signal import SignalType
            user_prs = [s for s in self.signals if s.actor == user
                       and s.type == SignalType.PR_OPENED
                       and s.timestamp > now - timedelta(hours=24)]
            if user_prs:
                scores["preparing_release"] = scores.get("preparing_release", 0) + 0.3
                reasons.setdefault("preparing_release", []).append(
                    f"User opened {len(user_prs)} PR(s) in the last 24h"
                )

        if active_app == "jira":
            scores["approval_decision"] = scores.get("approval_decision", 0) + 0.3
            reasons.setdefault("approval_decision", []).append("Jira is active — may be reviewing approvals")

        if active_app == "email":
            scores["customer_check_in"] = scores.get("customer_check_in", 0) + 0.2
            reasons.setdefault("customer_check_in", []).append("Email is active")

        if active_app == "slack":
            from maestro_oem.signal import SignalType
            recent_questions = [s for s in self.signals
                               if s.type == SignalType.QUESTION_ASKED
                               and s.timestamp > now - timedelta(hours=1)]
            if recent_questions:
                scores["knowledge_hunting"] = scores.get("knowledge_hunting", 0) + 0.5
                reasons.setdefault("knowledge_hunting", []).append(
                    f"Recent questions asked in Slack — likely searching for knowledge"
                )

        if active_app == "crm":
            scores["customer_check_in"] = scores.get("customer_check_in", 0) + 0.5
            reasons.setdefault("customer_check_in", []).append("CRM is active")

        # ─── Time-based inference ──────────────────────────────────────────
        hour = now.hour
        if 6 <= hour <= 10:
            scores["daily_triage"] = scores.get("daily_triage", 0) + 0.3
            reasons.setdefault("daily_triage", []).append("Morning hours — likely daily triage")

        # ─── OEM state-based inference ─────────────────────────────────────
        # Pending recommendations → approval decision
        try:
            from maestro_oem.decision import DecisionEngine
            from maestro_oem.evidence_graph import EvidenceGraph
            eg = EvidenceGraph()
            eg.build_from_model(self.model)
            de = DecisionEngine(self.model, eg)
            recs = de.get_recommendations()
            if recs:
                scores["approval_decision"] = scores.get("approval_decision", 0) + 0.2
                reasons.setdefault("approval_decision", []).append(
                    f"{len(recs)} active recommendations pending decisions"
                )
        except Exception:
            pass

        # Recent incidents → resolving incident
        from maestro_oem.signal import SignalType
        recent_incidents = [s for s in self.signals
                           if s.type in (SignalType.INCIDENT,)
                           and s.timestamp > now - timedelta(hours=24)]
        if recent_incidents:
            scores["resolving_incident"] = scores.get("resolving_incident", 0) + 0.8
            reasons.setdefault("resolving_incident", []).append(
                f"{len(recent_incidents)} incident(s) in the last 24h"
            )

        # Customer drift → customer check-in
        drift_signals = [s for s in self.signals
                        if s.type == SignalType.CUSTOMER_CHAMPION_QUIET
                        and s.timestamp > now - timedelta(days=7)]
        if drift_signals and active_app in ("email", "calendar", "crm"):
            scores["customer_check_in"] = scores.get("customer_check_in", 0) + 0.4
            reasons.setdefault("customer_check_in", []).append(
                f"Customer drift signals active — relationship may need attention"
            )

        # ─── URL-based inference ───────────────────────────────────────────
        if url_context:
            domain = url_context.lower()
            if "github.com" in domain:
                scores["reviewing_code"] = scores.get("reviewing_code", 0) + 0.3
                reasons.setdefault("reviewing_code", []).append("GitHub URL detected")
            if "atlassian" in domain or "jira" in domain:
                scores["approval_decision"] = scores.get("approval_decision", 0) + 0.3
            if "salesforce" in domain or "hubspot" in domain:
                scores["customer_check_in"] = scores.get("customer_check_in", 0) + 0.4

        # ─── Select the top intent ─────────────────────────────────────────
        if not scores:
            return {
                "intent": "unknown",
                "label": "Unknown intent",
                "confidence": 0.0,
                "why": ["No context signals available to infer intent."],
                "what_maestro_knows": {},
                "recommended_whisper": None,
                "alternative_intents": [],
            }

        sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_intent, top_score = sorted_intents[0]
        confidence = min(1.0, top_score)

        # Normalize: if score > 1.0, scale down
        if confidence > 1.0:
            confidence = 1.0

        alternatives = [
            {"intent": k, "label": INTENTS.get(k, {}).get("label", k), "confidence": round(min(1.0, v), 4)}
            for k, v in sorted_intents[1:4]
        ]

        what_maestro_knows = self._gather_relevant_knowledge(top_intent, user)
        recommended_whisper = self._recommend_whisper(top_intent, user)

        return {
            "intent": top_intent,
            "label": INTENTS.get(top_intent, {}).get("label", top_intent),
            "description": INTENTS.get(top_intent, {}).get("description", ""),
            "confidence": round(confidence, 4),
            "why": reasons.get(top_intent, []),
            "what_maestro_knows": what_maestro_knows,
            "recommended_whisper": recommended_whisper,
            "alternative_intents": alternatives,
            "timestamp": now.isoformat(),
        }

    def _gather_relevant_knowledge(self, intent: str, user: str) -> dict[str, Any]:
        """Gather OEM knowledge relevant to the inferred intent."""
        knowledge: dict[str, Any] = {}

        if intent == "preparing_for_negotiation":
            # Surface customer relationships at risk
            from maestro_oem.signal import SignalType
            drift_customers = set()
            for s in self.signals:
                if s.type == SignalType.CUSTOMER_CHAMPION_QUIET:
                    drift_customers.add(s.metadata.get("customer", ""))
            if drift_customers:
                knowledge["at_risk_customers"] = list(drift_customers)

            # Surface open commitments
            commitments = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_MADE]
            if commitments:
                knowledge["open_commitments"] = len(commitments)

        elif intent == "reviewing_code":
            # Surface relevant laws
            eng_laws = [l.code for l in self.model.laws.values()
                       if "bottleneck" in l.statement.lower() or "review" in l.statement.lower()]
            if eng_laws:
                knowledge["relevant_laws"] = eng_laws

        elif intent == "approval_decision":
            # Surface bottlenecks
            try:
                bottlenecks = self.model.approvals.get_bottlenecks(min_count=2)
                if bottlenecks:
                    knowledge["bottlenecks"] = [{"gate": b["gate"], "count": b["items_gated"]} for b in bottlenecks]
            except Exception:
                pass

        elif intent == "daily_triage":
            # Surface recommendation count
            try:
                from maestro_oem.decision import DecisionEngine
                from maestro_oem.evidence_graph import EvidenceGraph
                eg = EvidenceGraph()
                eg.build_from_model(self.model)
                de = DecisionEngine(self.model, eg)
                recs = de.get_recommendations()
                knowledge["pending_decisions"] = len(recs)
            except Exception:
                pass

        return knowledge

    def _recommend_whisper(self, intent: str, user: str) -> dict[str, Any] | None:
        """Recommend what to whisper to the user without being asked."""
        whispers = {
            "preparing_for_negotiation": {
                "text": "Review customer relationship memory before the meeting. Maestro has tracked commitments, objections, and drift signals.",
                "action": "Open the Customer Judgment surface for the relevant customer.",
                "endpoint": "/api/oem/customer/list",
            },
            "reviewing_code": {
                "text": "Check for relevant organizational laws before approving. Maestro has detected patterns in review bottlenecks.",
                "action": "Open the Laws surface to see relevant patterns.",
                "endpoint": "/api/oem/laws",
            },
            "preparing_release": {
                "text": "Review incident history and concentration risks before shipping.",
                "action": "Open the Knowledge Flow surface.",
                "endpoint": "/api/oem/knowledge",
            },
            "resolving_incident": {
                "text": "Check who has expertise in the affected domain. Maestro tracks hidden experts.",
                "action": "Open the Knowledge surface to find the right person.",
                "endpoint": "/api/oem/knowledge",
            },
            "board_update_preparation": {
                "text": "Use the daily narrative and pulse for your board update. Maestro has already composed the story.",
                "action": "Open the Narrative and Pulse panels.",
                "endpoint": "/api/oem/narrative",
            },
            "approval_decision": {
                "text": "Check the Time Machine for similar past approvals before deciding.",
                "action": "Open the Time Machine.",
                "endpoint": "/api/oem/time-machine",
            },
            "customer_check_in": {
                "text": "Review the Morning Brief for customers needing attention today.",
                "action": "Open the Customer Morning Brief.",
                "endpoint": "/api/oem/customer/morning",
            },
            "strategic_planning": {
                "text": "Review the Cognitive Load Engine and organizational pulse before planning.",
                "action": "Open the Pulse and Cognitive Load panels.",
                "endpoint": "/api/oem/pulse",
            },
            "daily_triage": {
                "text": "Review the 3 things that matter today. Maestro has already prioritized.",
                "action": "Open the Morning Brief.",
                "endpoint": "/api/oem/customer/morning",
            },
            "knowledge_hunting": {
                "text": "Check the Knowledge Flow surface for who knows what.",
                "action": "Open the Knowledge surface.",
                "endpoint": "/api/oem/knowledge",
            },
        }
        return whispers.get(intent)
