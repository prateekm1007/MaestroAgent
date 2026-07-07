"""Phase 9 — Ambient Signal Fusion tests.

Tests CalendarAwarenessEngine + CommitmentEscalationEngine.

Gate: both engines must produce substantive output with evidence.
"""

from __future__ import annotations

import sys, pathlib, os
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone

import pytest


class TestCalendarAwarenessEngine:
    """Phase 9.1: Calendar Awareness Engine."""

    def _make_engine(self):
        from maestro_oem.calendar_awareness import CalendarAwarenessEngine
        return CalendarAwarenessEngine(oem_state=None, calendar_source=None)

    def test_meeting_urgency_classification(self):
        """Meeting urgency is correctly classified."""
        engine = self._make_engine()
        now = datetime.now(timezone.utc)

        assert engine._compute_urgency(now + timedelta(minutes=2), now).value == "now"
        assert engine._compute_urgency(now + timedelta(minutes=15), now).value == "imminent"
        assert engine._compute_urgency(now + timedelta(minutes=60), now).value == "soon"
        assert engine._compute_urgency(now + timedelta(hours=6), now).value == "today"
        assert engine._compute_urgency(now + timedelta(hours=24), now).value == "upcoming"
        assert engine._compute_urgency(now + timedelta(hours=72), now).value == "future"

    def test_entity_extraction_from_title(self):
        """Entity is extracted from meeting title."""
        engine = self._make_engine()
        engine.KNOWN_ENTITIES = ["Globex"]  # configured per-deployment
        event = {"title": "Q3 Renewal — Globex Corp", "attendees": []}
        assert engine._extract_entity(event) == "Globex"

    def test_entity_extraction_from_attendee_domain(self):
        """Entity is extracted from attendee email domain."""
        engine = self._make_engine()
        event = {"title": "Meeting", "attendees": ["raj@initech.com"]}
        assert engine._extract_entity(event) == "Initech"

    def test_talking_points_have_evidence(self):
        """Every talking point has an evidence source (anti-Cluely)."""
        engine = self._make_engine()
        attendee_profiles = [
            {"email": "raj@globex.com", "interaction_count": 5, "last_interaction_days_ago": 20,
             "topics": ["SSO"], "evidence": {"source": "oem_signal_history", "count": 5}},
        ]
        points = engine._generate_talking_points(
            entity="Globex",
            attendee_profiles=attendee_profiles,
            open_commitments=[],
            overdue_commitments=[],
        )
        for p in points:
            assert p.get("evidence"), f"Talking point missing evidence: {p}"
            assert p["evidence"].get("source"), f"Evidence missing source: {p}"

    def test_preparation_gap_alert(self):
        """Preparation gap alert fires for unprepared imminent meetings."""
        engine = self._make_engine()
        from maestro_oem.calendar_awareness import MeetingContext, MeetingUrgency, PreparationStatus

        now = datetime.now(timezone.utc)
        ctx = MeetingContext(
            meeting_id="test-1",
            title="Urgent Meeting",
            start_time=now + timedelta(minutes=10),
            end_time=now + timedelta(minutes=40),
            attendees=[],
            urgency=MeetingUrgency.IMMINENT,
            preparation_status=PreparationStatus.NOT_STARTED,
        )
        engine._contexts["test-1"] = ctx

        alerts = engine.get_preparation_gap_alerts()
        assert len(alerts) == 1
        assert alerts[0]["type"] == "preparation_gap"
        assert "no preparation done" in alerts[0]["message"]

    def test_meeting_context_to_dict(self):
        """MeetingContext serializes correctly."""
        from maestro_oem.calendar_awareness import MeetingContext, MeetingUrgency, PreparationStatus
        now = datetime.now(timezone.utc)
        ctx = MeetingContext(
            meeting_id="test-2",
            title="Test",
            start_time=now,
            end_time=now + timedelta(hours=1),
            attendees=["a@b.com"],
            urgency=MeetingUrgency.SOON,
            preparation_status=PreparationStatus.READY,
            entity="Globex",
        )
        d = ctx.to_dict()
        assert d["entity"] == "Globex"
        assert d["urgency"] == "soon"
        assert d["preparation_status"] == "ready"


class TestCommitmentEscalationEngine:
    """Phase 9.2: Commitment Escalation Engine."""

    def _make_engine(self):
        from maestro_oem.commitment_escalation import CommitmentEscalationEngine
        return CommitmentEscalationEngine(oem_state=None)

    def test_health_classification(self):
        """Commitment health is correctly classified."""
        engine = self._make_engine()
        from maestro_oem.commitment_escalation import CommitmentHealth

        assert engine._compute_health(10, None) == CommitmentHealth.ON_TRACK
        assert engine._compute_health(5, None) == CommitmentHealth.APPROACHING
        assert engine._compute_health(2, None) == CommitmentHealth.URGENT
        assert engine._compute_health(0, 1) == CommitmentHealth.OVERDUE
        assert engine._compute_health(None, None) == CommitmentHealth.ON_TRACK

    def test_escalation_level(self):
        """Escalation level matches health."""
        engine = self._make_engine()
        from maestro_oem.commitment_escalation import CommitmentHealth, EscalationLevel

        assert engine._compute_escalation_level(CommitmentHealth.ON_TRACK, None) == EscalationLevel.NONE
        assert engine._compute_escalation_level(CommitmentHealth.APPROACHING, None) == EscalationLevel.LOW
        assert engine._compute_escalation_level(CommitmentHealth.URGENT, None) == EscalationLevel.MEDIUM
        assert engine._compute_escalation_level(CommitmentHealth.OVERDUE, 3) == EscalationLevel.HIGH
        assert engine._compute_escalation_level(CommitmentHealth.OVERDUE, 10) == EscalationLevel.CRITICAL

    def test_failure_prediction_sso(self):
        """SSO commitments get 73% failure prediction (the spec's example)."""
        engine = self._make_engine()
        prob, reason = engine._predict_failure(
            {"text": "Deploy SSO integration by Friday", "actor": "raj@globex.com"},
            CommitmentHealth := __import__("maestro_oem.commitment_escalation", fromlist=["CommitmentHealth"]).CommitmentHealth.ON_TRACK,
        )
        assert prob == 0.73
        assert "SSO" in reason or "sso" in reason.lower()
        assert "73%" in reason

    def test_nudge_generation_critical(self):
        """Critical escalation generates email nudge with draft."""
        engine = self._make_engine()
        commit = {
            "text": "Deliver SSO by Friday",
            "actor": "raj@globex.com",
            "entity": "Globex",
            "due_date": datetime.now(timezone.utc) - timedelta(days=10),
        }
        esc = engine.evaluate_commitment(commit)
        assert esc.escalation_level.value == "critical"
        assert esc.nudge_channel == "email"
        assert esc.nudge_draft is not None
        assert "Urgent" in esc.nudge_draft or "CRITICAL" in esc.nudge_draft

    def test_nudge_generation_medium_slack(self):
        """Medium escalation generates Slack nudge."""
        engine = self._make_engine()
        commit = {
            "text": "Send pricing options",
            "actor": "jane@acme.com",
            "entity": "Initech",
            "due_date": datetime.now(timezone.utc) + timedelta(days=2),
        }
        esc = engine.evaluate_commitment(commit)
        assert esc.escalation_level.value == "medium"
        assert esc.nudge_channel == "slack"
        assert esc.nudge_text is not None

    def test_escalation_to_dict(self):
        """Escalation serializes correctly."""
        engine = self._make_engine()
        commit = {
            "text": "Deploy SSO",
            "actor": "raj@globex.com",
            "entity": "Globex",
            "due_date": datetime.now(timezone.utc) + timedelta(days=5),
        }
        esc = engine.evaluate_commitment(commit)
        d = esc.to_dict()
        assert d["entity"] == "Globex"
        assert "health" in d
        assert "escalation_level" in d

    def test_commitment_has_evidence(self):
        """Every escalation has traceable evidence (anti-Cluely)."""
        engine = self._make_engine()
        commit = {
            "text": "Deploy SSO by Friday",
            "actor": "raj@globex.com",
            "entity": "Globex",
            "due_date": datetime.now(timezone.utc) - timedelta(days=3),
        }
        esc = engine.evaluate_commitment(commit)
        # The escalation must have either failure_probability or days_overdue as evidence
        assert esc.days_overdue is not None or esc.failure_probability is not None
        # The nudge must cite the specific commitment
        if esc.nudge_draft:
            assert "SSO" in esc.nudge_draft or "commitment" in esc.nudge_draft.lower()


class TestPhase9L0NoRegression:
    """Phase 9 must not regress the L0 substrate."""

    def test_situation_snapshot_27_fields(self):
        """L0.1: SituationSnapshot still has 27 fields."""
        from maestro_oem.situation import Situation
        import dataclasses
        fields = [f.name for f in dataclasses.fields(Situation)]
        assert len(fields) == 27

    def test_outcome_ledger_functional(self):
        """L0.2: OutcomeLedger still works."""
        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

    def test_classifier_new_types(self):
        """L0.3: Classifier still handles new types."""
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO by Q4.") == "tentative"
