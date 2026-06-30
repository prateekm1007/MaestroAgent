"""Executive Feed — a live stream of meaningful organizational events.

NOT notifications. NOT a log. A Bloomberg-terminal-style feed of only
the events that matter to executives:

  - Knowledge discovered (new law promoted, new expert identified)
  - Decision contradicted (a law was challenged)
  - Law strengthened / invalidated
  - Expert overloaded (bottleneck forming)
  - Customer drifting / champion quiet
  - Simulation confidence improved
  - Prediction resolved (correct or incorrect)
  - Pattern invalidated
  - Commitment broken
  - Concentration risk emerged

The feed suppresses low-value noise. Every event includes:
  - what happened
  - why it matters
  - business impact
  - recommended action
  - confidence
  - timestamp

Like a Bloomberg Terminal for organizational execution.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID


class FeedEvent:
    """A single meaningful organizational event."""

    def __init__(
        self,
        event_type: str,
        title: str,
        description: str,
        why_it_matters: str,
        business_impact: str,
        recommended_action: str,
        confidence: float,
        timestamp: datetime | None = None,
        entity_id: str = "",
        entity_type: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.event_type = event_type
        self.title = title
        self.description = description
        self.why_it_matters = why_it_matters
        self.business_impact = business_impact
        self.recommended_action = recommended_action
        self.confidence = confidence
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.evidence = evidence or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "why_it_matters": self.why_it_matters,
            "business_impact": self.business_impact,
            "recommended_action": self.recommended_action,
            "confidence": round(self.confidence, 4),
            "timestamp": self.timestamp.isoformat(),
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "evidence": self.evidence,
        }


class ExecutiveFeed:
    """Generates a meaningful event feed from the OEM state.

    The feed is derived from the current model state — it surfaces what's
    CHANGED or what's NOTABLE right now, not a raw log of every signal.

    Usage:
        feed = ExecutiveFeed(model, signals)
        events = feed.generate(limit=20)
    """

    def __init__(self, model: Any, signals: list) -> None:
        self.model = model
        self.signals = signals

    def generate(self, limit: int = 20) -> list[dict[str, Any]]:
        """Generate the executive feed.

        Returns the most meaningful events, sorted by impact.
        """
        events: list[FeedEvent] = []

        events.extend(self._law_events())
        events.extend(self._customer_drift_events())
        events.extend(self._commitment_events())
        events.extend(self._bottleneck_events())
        events.extend(self._concentration_risk_events())
        events.extend(self._decision_events())
        events.extend(self._prediction_events())

        # Sort by timestamp descending, then by confidence
        events.sort(key=lambda e: e.timestamp, reverse=True)

        return [e.to_dict() for e in events[:limit]]

    def _law_events(self) -> list[FeedEvent]:
        """Surface law promotions and invalidations."""
        events = []
        for law in self.model.laws.values():
            # Newly promoted laws (high confidence, recent)
            if law.confidence > 0.9 and law.validated_runtimes >= 3:
                events.append(FeedEvent(
                    event_type="law_strengthened",
                    title=f"Law strengthened: {law.code}",
                    description=law.statement[:120],
                    why_it_matters=f"This organizational pattern has been validated {law.validated_runtimes} times with {law.failed_runtimes} failures.",
                    business_impact="Confidence in this pattern is high — future recommendations based on it are more reliable.",
                    recommended_action="Consider operationalizing this law into a documented process.",
                    confidence=law.confidence,
                    timestamp=law.last_validated or datetime.now(timezone.utc),
                    entity_id=law.code,
                    entity_type="law",
                    evidence={"validated_runtimes": law.validated_runtimes,
                              "failed_runtimes": law.failed_runtimes},
                ))

            # Invalidated or stressed laws
            if hasattr(law, 'status') and law.status.value in ("invalidated", "stressed"):
                status = law.status.value
                events.append(FeedEvent(
                    event_type="law_invalidated" if status == "invalidated" else "law_challenged",
                    title=f"Law {status}: {law.code}",
                    description=law.statement[:120],
                    why_it_matters=f"This organizational pattern is {status}. {law.failed_runtimes} failures detected.",
                    business_impact="Recommendations based on this law should be treated with lower confidence.",
                    recommended_action="Review the pattern and update or retire the law.",
                    confidence=law.confidence,
                    timestamp=law.last_validated or datetime.now(timezone.utc),
                    entity_id=law.code,
                    entity_type="law",
                    evidence={"status": status, "failed_runtimes": law.failed_runtimes},
                ))

        return events

    def _customer_drift_events(self) -> list[FeedEvent]:
        """Surface customer relationship drift."""
        from maestro_oem.signal import SignalType
        events = []

        # Group drift signals by customer
        drift_by_customer: dict[str, list] = {}
        for s in self.signals:
            if s.type == SignalType.CUSTOMER_CHAMPION_QUIET:
                customer = s.metadata.get("customer", "unknown")
                drift_by_customer.setdefault(customer, []).append(s)

        for customer, drift_sigs in drift_by_customer.items():
            arr = sum(float(s.metadata.get("arr_impact", 0) or 0) for s in drift_sigs)
            events.append(FeedEvent(
                event_type="customer_drifting",
                title=f"{customer} champion has gone quiet",
                description=f"{drift_sigs[0].metadata.get('contact', 'Champion')} at {customer} has gone silent.",
                why_it_matters="Champion disengagement is the strongest leading indicator of relationship decay.",
                business_impact=f"${arr:,.0f} ARR at stake." if arr else "ARR impact unknown.",
                recommended_action="Schedule a check-in with the champion. Identify if a competitor is influencing the relationship.",
                confidence=0.7,
                timestamp=drift_sigs[-1].timestamp,
                entity_id=customer,
                entity_type="customer",
                evidence={"drift_signals": len(drift_sigs), "arr_at_stake": arr},
            ))

        return events

    def _commitment_events(self) -> list[FeedEvent]:
        """Surface broken commitments."""
        from maestro_oem.signal import SignalType
        events = []

        for s in self.signals:
            if s.type == SignalType.CUSTOMER_COMMITMENT_BROKEN:
                customer = s.metadata.get("customer", "unknown")
                commitment = s.metadata.get("commitment", "a commitment")
                arr = float(s.metadata.get("arr_impact", 0) or 0)
                events.append(FeedEvent(
                    event_type="commitment_broken",
                    title=f"Broken commitment to {customer}",
                    description=f"Missed promise: {commitment[:80]}",
                    why_it_matters="Broken commitments erode trust and predict renewal failure.",
                    business_impact=f"${arr:,.0f} ARR at stake." if arr else "Trust impact: negative.",
                    recommended_action="Acknowledge the miss, provide a new timeline, and deliver on the next commitment.",
                    confidence=1.0,
                    timestamp=s.timestamp,
                    entity_id=customer,
                    entity_type="customer",
                    evidence={"commitment": commitment, "arr_at_stake": arr},
                ))

        return events

    def _bottleneck_events(self) -> list[FeedEvent]:
        """Surface approval bottlenecks."""
        events = []
        try:
            bottlenecks = self.model.approvals.get_bottlenecks(min_count=3)
            for bn in bottlenecks:
                gate = bn["gate"]
                count = bn["items_gated"]
                events.append(FeedEvent(
                    event_type="expert_overloaded",
                    title=f"{gate} is becoming a bottleneck",
                    description=f"{gate} gates {count} items — approval load is concentrating.",
                    why_it_matters="Bottlenecks slow execution and create single points of failure.",
                    business_impact=f"{count} items are blocked behind this gate.",
                    recommended_action="Redistribute approval authority or streamline the gate.",
                    confidence=0.8,
                    timestamp=datetime.now(timezone.utc),
                    entity_id=gate,
                    entity_type="person",
                    evidence={"items_gated": count},
                ))
        except Exception:
            pass

        return events

    def _concentration_risk_events(self) -> list[FeedEvent]:
        """Surface knowledge concentration risks (bus-factor)."""
        events = []
        try:
            risks = self.model.knowledge.get_concentration_risk()
            for domain, score in risks.items():
                events.append(FeedEvent(
                    event_type="concentration_risk",
                    title=f"Bus-factor risk in {domain}",
                    description=f"Knowledge in {domain} is concentrated in one person.",
                    why_it_matters="If this person leaves, the organization loses critical expertise.",
                    business_impact=f"Departure would degrade outcomes in {domain}.",
                    recommended_action="Cross-train or document critical knowledge in this domain.",
                    confidence=0.75,
                    timestamp=datetime.now(timezone.utc),
                    entity_id=domain,
                    entity_type="domain",
                    evidence={"influence_score": score},
                ))
        except Exception:
            pass

        return events

    def _decision_events(self) -> list[FeedEvent]:
        """Surface recent customer decisions (renewals, churns)."""
        from maestro_oem.signal import SignalType
        events = []

        for s in self.signals:
            if s.type == SignalType.CUSTOMER_DECISION:
                customer = s.metadata.get("customer", "unknown")
                outcome = s.metadata.get("decision_outcome", "unknown")
                arr = float(s.metadata.get("arr_impact", 0) or 0)
                if outcome == "renewed":
                    events.append(FeedEvent(
                        event_type="customer_renewed",
                        title=f"{customer} renewed",
                        description=f"Customer {customer} decided to renew.",
                        why_it_matters="Renewal validates the relationship and the product.",
                        business_impact=f"${arr:,.0f} ARR secured." if arr else "Revenue secured.",
                        recommended_action="Identify upsell opportunities from the healthy relationship.",
                        confidence=1.0,
                        timestamp=s.timestamp,
                        entity_id=customer,
                        entity_type="customer",
                        evidence={"outcome": outcome, "arr": arr},
                    ))
                elif outcome == "churned":
                    events.append(FeedEvent(
                        event_type="customer_churned",
                        title=f"{customer} churned",
                        description=f"Customer {customer} decided not to renew.",
                        why_it_matters="Churn signals a pattern that may repeat.",
                        business_impact=f"${arr:,.0f} ARR lost." if arr else "Revenue lost.",
                        recommended_action="Conduct loss review. Analyze the pattern to prevent recurrence.",
                        confidence=1.0,
                        timestamp=s.timestamp,
                        entity_id=customer,
                        entity_type="customer",
                        evidence={"outcome": outcome, "arr": arr},
                    ))

        return events

    def _prediction_events(self) -> list[FeedEvent]:
        """Surface resolved predictions (learning loop outcomes)."""
        events = []
        try:
            import os
            from pathlib import Path
            from maestro_oem.prediction_lifecycle import ClosedLoopLearningManager
            from maestro_oem.learning import CalibrationEngine

            db_path = os.environ.get(
                "MAESTRO_LEARNING_DB",
                get_db_url_for_learning(),
            )
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            cal = CalibrationEngine(db_path)
            manager = ClosedLoopLearningManager(
                db_path, self.model, self.signals, cal,
                contradiction_log=getattr(self.model, '_contradiction_log', None),
            )
            report = manager.get_improvement_report()
            recent_preds = report.get("recent_predictions", [])

            for pred in recent_preds[:5]:
                if pred.get("status") in ("correct", "incorrect"):
                    status = pred["status"]
                    entity = pred.get("entity_id", "unknown")
                    confidence = pred.get("confidence", 0)
                    events.append(FeedEvent(
                        event_type="prediction_resolved",
                        title=f"Prediction {status}: {entity[:50]}",
                        description=f"Maestro predicted this with {confidence:.0%} confidence. Outcome: {status}.",
                        why_it_matters="Each resolved prediction improves Maestro's calibration.",
                        business_impact="The learning loop is getting smarter." if status == "correct"
                                        else "The prediction was wrong — calibration will adjust.",
                        recommended_action="No action needed — the loop is self-correcting.",
                        confidence=confidence,
                        timestamp=datetime.fromisoformat(pred.get("resolved_at", "").replace("Z", "+00:00"))
                                   if pred.get("resolved_at") else datetime.now(timezone.utc),
                        entity_id=pred.get("prediction_id", ""),
                        entity_type="prediction",
                        evidence={"predicted_confidence": confidence, "outcome": status},
                    ))
        except Exception:
            pass

        return events
