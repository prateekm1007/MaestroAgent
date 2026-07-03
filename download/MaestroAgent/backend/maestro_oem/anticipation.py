"""The Anticipation Engine — Maestro's ability to simulate tomorrow.

CEO's vision (2026-07-03): "Every night Maestro should simulate tomorrow.
Tomorrow's meetings, risks, deadlines, likely questions, blockers, customers,
commitments, politics. Then tomorrow morning everything is already prepared.

That is the difference between Assistant and Chief of Staff."

The Anticipation Engine runs nightly to anticipate what will matter tomorrow.
It feeds the Preparation Engine and the Future Memory store.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


class AnticipationEngine:
    """Simulate tomorrow — anticipate what will matter before it happens.

    Usage:
        engine = AnticipationEngine(model, signals)
        anticipation = engine.anticipate_tomorrow(org_id="default")
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def anticipate_tomorrow(self, org_id: str = "default") -> dict[str, Any]:
        """Anticipate what will matter tomorrow.

        Returns:
        {
            "date": "2026-07-04",
            "meetings": [...],
            "risks": [...],
            "deadlines": [...],
            "blockers": [...],
            "customers": [...],
            "commitments": [...],
        }
        """
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

        return {
            "date": tomorrow,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "meetings": self._anticipated_meetings(),
            "risks": self._anticipated_risks(),
            "deadlines": self._upcoming_deadlines(),
            "blockers": self._current_blockers(),
            "customers": self._customers_needing_attention(),
            "commitments": self._commitments_at_risk(),
        }

    def _anticipated_meetings(self) -> list[dict[str, Any]]:
        """Anticipate tomorrow's meetings and likely questions."""
        from maestro_oem.signal import SignalType

        customers = set()
        for s in self.signals:
            if hasattr(s, "metadata") and s.metadata.get("customer"):
                customers.add(s.metadata["customer"])

        meetings = []
        for customer in list(customers)[:3]:
            # What objections has this customer raised? Those are likely questions.
            likely_questions = []
            customer_signals = [s for s in self.signals
                               if s.metadata.get("customer") == customer]
            for s in customer_signals:
                if s.type == SignalType.CUSTOMER_OBJECTION:
                    obj = s.metadata.get("objection_type", "")
                    if obj:
                        likely_questions.append(obj)

            meetings.append({
                "title": f"{customer} review",
                "entity": customer,
                "likely_questions": likely_questions[:3],
            })

        return meetings

    def _anticipated_risks(self) -> list[dict[str, Any]]:
        """What could go wrong tomorrow?"""
        from maestro_oem.signal import SignalType

        risks = []

        # Broken commitments
        broken = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
        for s in broken[:2]:
            risks.append({
                "type": "broken_commitment",
                "description": f"{s.metadata.get('customer', '')} has a broken commitment",
                "severity": "high",
            })

        # Champion quiet
        quiet = [s for s in self.signals if s.type == SignalType.CUSTOMER_CHAMPION_QUIET]
        for s in quiet[:2]:
            risks.append({
                "type": "champion_quiet",
                "description": f"{s.metadata.get('customer', '')} champion has gone quiet",
                "severity": "medium",
            })

        # Concentration risks
        try:
            from maestro_oem.knowledge import KnowledgeGraph
            kg = KnowledgeGraph(self.model, self.signals)
            for risk in kg.concentration_risks[:2]:
                risks.append({
                    "type": "concentration_risk",
                    "description": f"{risk.get('domain', '')} has concentration score {risk.get('score', 0):.2f}",
                    "severity": "medium",
                })
        except Exception:
            pass

        return risks

    def _upcoming_deadlines(self) -> list[dict[str, Any]]:
        """What's due tomorrow or soon?"""
        deadlines = []

        # Check for commitments with dates
        from maestro_oem.signal import SignalType
        commitments = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_MADE]
        for s in commitments[:3]:
            commitment = s.metadata.get("commitment", "")
            deadlines.append({
                "description": commitment[:80],
                "customer": s.metadata.get("customer", ""),
                "status": "upcoming",
            })

        return deadlines

    def _current_blockers(self) -> list[dict[str, Any]]:
        """What's stuck right now?"""
        blockers = []

        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=2) if hasattr(self.model, "approvals") else []
            for bn in bottlenecks[:3]:
                blockers.append({
                    "person": bn["gate"],
                    "items_gated": bn["items_gated"],
                    "description": f"{bn['gate']} is gating {bn['items_gated']} items",
                })
        except Exception:
            pass

        return blockers

    def _customers_needing_attention(self) -> list[dict[str, Any]]:
        """Which customers need attention tomorrow?"""
        from maestro_oem.signal import SignalType

        customers = []
        seen = set()

        # Customers with objections
        for s in self.signals:
            if s.type == SignalType.CUSTOMER_OBJECTION:
                c = s.metadata.get("customer", "")
                if c and c not in seen:
                    seen.add(c)
                    customers.append({
                        "customer": c,
                        "reason": "Has open objections",
                        "priority": "high",
                    })

        # Customers with broken commitments
        for s in self.signals:
            if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
                c = s.metadata.get("customer", "")
                if c and c not in seen:
                    seen.add(c)
                    customers.append({
                        "customer": c,
                        "reason": "Has broken commitments",
                        "priority": "high",
                    })

        return customers[:5]

    def _commitments_at_risk(self) -> list[dict[str, Any]]:
        """Which commitments are at risk?"""
        from maestro_oem.signal import SignalType

        at_risk = []
        broken = [s for s in self.signals if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN]
        for s in broken[:3]:
            at_risk.append({
                "customer": s.metadata.get("customer", ""),
                "commitment": s.metadata.get("commitment", ""),
                "status": "broken",
            })

        return at_risk
