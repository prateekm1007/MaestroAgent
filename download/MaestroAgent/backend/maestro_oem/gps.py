"""Organizational GPS — every employee always knows where they are.

Like Google Maps for organizational execution. Every user should be
able to answer:
  - Where am I in this workflow?
  - What is blocking progress?
  - Who has the knowledge I need?
  - What should happen next?

The GPS is NOT a dashboard. It's a navigation system that gives each
user a personalized view of their current position in the organization's
execution flow, with directions to the next step.

Different people see different things:
  - CEO: 3 strategic decisions, organizational pulse
  - Engineer: 2 blockers, who knows what, what's next
  - Manager: 1 approval pending, team status
  - Analyst: data quality, missing signals

The GPS uses the user's email to personalize the view — it finds the
signals, LOs, and recommendations that involve them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class OrganizationalGPS:
    """Personalized organizational navigation for each user.

    Usage:
        gps = OrganizationalGPS(model, signals, decisions)
        position = gps.locate("priya.m@example.com")
        # position = {where_am_i, blocking, who_knows, whats_next}
    """

    def __init__(self, model: Any, signals: list, decisions: Any = None) -> None:
        self.model = model
        self.signals = signals
        self.decisions = decisions

    def locate(self, user_email: str) -> dict[str, Any]:
        """Locate a user in the organizational execution flow.

        Returns:
          - where_am_i: current position description
          - blocking: what's blocking this user's progress
          - who_knows: who has the knowledge this user might need
          - whats_next: recommended next action
          - my_signals: recent signals involving this user
          - my_recommendations: active recommendations for this user
          - my_commitments: open commitments this user owns
          - cognitive_load: this user's current cognitive load score
        """
        user_signals = [s for s in self.signals if s.actor == user_email
                        or user_email in s.metadata.get("participants", [])
                        or s.metadata.get("contact") == user_email]

        blocking = self._find_blockers(user_email)
        who_knows = self._find_experts(user_email)
        whats_next = self._recommend_next(user_email, user_signals, blocking)
        my_recs = self._my_recommendations(user_email)
        my_commitments = self._my_commitments(user_email)

        return {
            "user": user_email,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "where_am_i": self._describe_position(user_email, user_signals),
            "blocking": blocking,
            "who_knows": who_knows,
            "whats_next": whats_next,
            "my_signals": [
                {
                    "type": s.type.value,
                    "timestamp": s.timestamp.isoformat(),
                    "artifact": s.artifact,
                }
                for s in sorted(user_signals, key=lambda s: s.timestamp, reverse=True)[:5]
            ],
            "my_recommendations": my_recs,
            "my_commitments": my_commitments,
            "cognitive_load": self._cognitive_load(user_email, user_signals, blocking),
        }

    def _describe_position(self, email: str, signals: list) -> str:
        """Describe where the user is in the workflow."""
        if not signals:
            return f"{email} has no recent signals in the OEM. They may be new or disconnected."

        recent = sorted(signals, key=lambda s: s.timestamp, reverse=True)
        last = recent[0]
        now = datetime.now(timezone.utc)
        days_ago = (now - last.timestamp).days

        # Build a time qualifier that reads naturally
        if days_ago == 0:
            time_q = "today"
        elif days_ago == 1:
            time_q = "yesterday"
        elif days_ago < 7:
            time_q = f"{days_ago}d ago"
        elif days_ago < 30:
            time_q = f"{days_ago // 7}w ago"
        elif days_ago < 365:
            time_q = f"{days_ago // 30}mo ago"
        else:
            time_q = f"{days_ago // 365}y ago"

        # Infer what they're working on from recent signal types
        from maestro_oem.signal import SignalType
        recent_types = [s.type for s in recent[:5]]

        if any(t in (SignalType.PR_OPENED, SignalType.PR_MERGED, SignalType.COMMIT) for t in recent_types):
            domain = recent[0].metadata.get("domain", "engineering")
            return f"Active in {domain} engineering. Last signal {time_q}."
        if any(t == SignalType.CUSTOMER_MEETING for t in recent_types):
            customer = recent[0].metadata.get("customer", "a customer")
            return f"Engaged with {customer}. Last meeting {time_q}."
        if any(t == SignalType.ISSUE_TRANSITIONED for t in recent_types):
            return f"In the delivery flow. Last Jira action {time_q}."
        if any(t == SignalType.MEETING_COMPLETED for t in recent_types):
            return f"In meetings/communication flow. Last meeting {time_q}."
        if any(t == SignalType.CUSTOMER_COMMITMENT_MADE for t in recent_types):
            customer = recent[0].metadata.get("customer", "a customer")
            return f"Owns commitments to {customer}. Last commitment {time_q}."
        if any(t == SignalType.CUSTOMER_OBJECTION for t in recent_types):
            customer = recent[0].metadata.get("customer", "a customer")
            return f"Handling objections from {customer}. Last signal {time_q}."

        return f"Active in the organization. Last signal {time_q}."

    def _find_blockers(self, email: str) -> list[dict[str, Any]]:
        """Find what's blocking this user's progress."""
        blockers = []

        # Is this user a bottleneck?
        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=2)
            for bn in bottlenecks:
                if bn["gate"] == email:
                    blockers.append({
                        "type": "approval_backlog",
                        "description": f"You have {bn['items_gated']} items waiting for your approval.",
                        "severity": "high" if bn["items_gated"] >= 5 else "medium",
                        "action": "Review and approve or delegate pending items.",
                    })
        except Exception:
            pass

        # Are they waiting on someone else's approval?
        # Check if they have open PRs or issues that haven't been approved
        from maestro_oem.signal import SignalType
        user_prs = [s for s in self.signals if s.actor == email and s.type == SignalType.PR_OPENED]
        if user_prs:
            recent_pr = user_prs[-1]
            days_open = (datetime.now(timezone.utc) - recent_pr.timestamp).days
            if days_open > 3:
                blockers.append({
                    "type": "waiting_for_review",
                    "description": f"Your PR {recent_pr.artifact} has been open for {days_open}d without review.",
                    "severity": "medium" if days_open < 7 else "high",
                    "action": "Follow up with the reviewer or request a different reviewer.",
                })

        # Are they waiting on a customer commitment?
        user_commitments = [s for s in self.signals
                           if s.actor == email and s.type == SignalType.CUSTOMER_COMMITMENT_MADE]
        for c in user_commitments:
            customer = c.metadata.get("customer", "")
            commitment = c.metadata.get("commitment", "")
            blockers.append({
                "type": "open_commitment",
                "description": f"You committed to {customer}: {commitment[:60]}",
                "severity": "medium",
                "action": "Track the due date and communicate proactively if at risk.",
            })

        return blockers

    def _find_experts(self, email: str) -> list[dict[str, Any]]:
        """Find who has the knowledge this user might need."""
        experts = []

        # Find domains the user works in
        from maestro_oem.signal import SignalType
        user_domains = set()
        for s in self.signals:
            if s.actor == email:
                domain = s.metadata.get("domain", "")
                if domain:
                    user_domains.add(domain)

        # Find experts in those domains
        for domain in user_domains:
            holders = self.model.knowledge.domain_holders.get(domain, set())
            for holder in holders:
                if holder != email:
                    experts.append({
                        "domain": domain,
                        "expert": holder,
                        "influence": self.model.knowledge.influence.get(holder, 0),
                        "why": f"{holder} has documented expertise in {domain}.",
                    })

        # Sort by influence
        experts.sort(key=lambda e: e["influence"], reverse=True)
        return experts[:5]

    def _recommend_next(self, email: str, signals: list, blockers: list) -> dict[str, Any]:
        """Recommend the single most important next action."""
        if blockers:
            top_blocker = blockers[0]
            return {
                "action": top_blocker["action"],
                "why": top_blocker["description"],
                "urgency": top_blocker["severity"],
            }

        # If no blockers, suggest based on recent activity
        from maestro_oem.signal import SignalType
        recent = sorted(signals, key=lambda s: s.timestamp, reverse=True)
        if recent:
            last = recent[0]
            if last.type == SignalType.PR_OPENED:
                return {
                    "action": "Follow up on your open PR.",
                    "why": "Code review is the fastest path to merge.",
                    "urgency": "normal",
                }
            if last.type == SignalType.CUSTOMER_MEETING:
                customer = last.metadata.get("customer", "the customer")
                return {
                    "action": f"Send a follow-up to {customer} with meeting notes.",
                    "why": "Timely follow-up maintains momentum after meetings.",
                    "urgency": "normal",
                }
            if last.type == SignalType.ISSUE_CREATED:
                return {
                    "action": "Triage the issue and assign priority.",
                    "why": "Untriaged issues create delivery uncertainty.",
                    "urgency": "normal",
                }

        return {
            "action": "No blocking items. Consider proactively documenting knowledge or mentoring.",
            "why": "Your execution path is clear.",
            "urgency": "low",
        }

    def _my_recommendations(self, email: str) -> list[dict[str, Any]]:
        """Find active recommendations that involve this user."""
        recs = []
        try:
            if self.decisions:
                all_recs = self.decisions.get_recommendations()
                for rec in all_recs:
                    # Check if this user is mentioned in the recommendation
                    if email in rec.title or email in rec.description or email in str(rec.provenance):
                        recs.append({
                            "title": rec.title,
                            "recommendation": rec.recommendation,
                            "confidence": round(rec.confidence, 4),
                            "urgency": rec.urgency,
                        })
        except Exception:
            pass

        return recs[:3]

    def _my_commitments(self, email: str) -> list[dict[str, Any]]:
        """Find open commitments this user owns."""
        from maestro_oem.signal import SignalType
        commitments = []
        for s in self.signals:
            if s.actor == email and s.type == SignalType.CUSTOMER_COMMITMENT_MADE:
                commitments.append({
                    "customer": s.metadata.get("customer", ""),
                    "commitment": s.metadata.get("commitment", ""),
                    "due_date": s.metadata.get("due_date", ""),
                    "status": "open",
                })
        return commitments

    def _cognitive_load(self, email: str, signals: list, blockers: list) -> dict[str, Any]:
        """Estimate this user's cognitive load.

        NOT a precise measurement — a heuristic based on:
          - Number of active blockers
          - Number of open commitments
          - Signal volume (context switching)
          - Time since last break (if inferrable)
        """
        score = 0

        # Blockers add load
        score += len(blockers) * 15

        # Open commitments add load
        from maestro_oem.signal import SignalType
        commitments = sum(1 for s in self.signals if s.actor == email
                         and s.type == SignalType.CUSTOMER_COMMITMENT_MADE)
        score += commitments * 10

        # Signal volume (context switching indicator)
        recent_signals = [s for s in signals if s.timestamp > datetime.now(timezone.utc) - timedelta(days=7)]
        score += min(30, len(recent_signals) * 3)

        # Multiple domains = context switching
        domains = set()
        for s in recent_signals:
            domain = s.metadata.get("domain", "")
            if domain:
                domains.add(domain)
        score += min(20, len(domains) * 5)

        score = min(100, score)

        if score < 30:
            level = "low"
        elif score < 60:
            level = "moderate"
        elif score < 80:
            level = "high"
        else:
            level = "overloaded"

        return {
            "score": score,
            "level": level,
            "factors": {
                "blockers": len(blockers),
                "open_commitments": commitments,
                "recent_signals": len(recent_signals),
                "domains_active": len(domains),
            },
        }
