"""Phase 17 - Workplace Signal Integration tests.

Tests the 7 privacy safeguards: company domain filter, sensitive category
exclusion, opt-out, private content marking, retention, access control,
audit logs. Plus L0 no-regression.
"""

from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from datetime import datetime, timedelta, timezone

import pytest


class TestDataGovernanceLayer:
    """Phase 17: Data Governance - 7 privacy safeguards."""

    def _make_governance(self, domain="acme.com"):
        from maestro_oem.workplace_signal_fusion import DataGovernanceLayer
        return DataGovernanceLayer(company_domain=domain)

    def test_safeguard_1_company_domain_filter(self):
        """Safeguard #1: Only company-domain emails are processed."""
        gov = self._make_governance("acme.com")
        assert gov.is_company_email("raj@acme.com") is True
        assert gov.is_company_email("raj@gmail.com") is False
        assert gov.is_company_email("raj@acme.com") is True

    def test_safeguard_2_sensitive_exclusion_hr(self):
        """Safeguard #2: HR emails are excluded."""
        gov = self._make_governance()
        is_sens, category = gov.is_sensitive("HR Update", "Your benefits enrollment")
        assert is_sens is True
        assert category == "hr"

    def test_safeguard_2_sensitive_exclusion_legal(self):
        """Safeguard #2: Legal emails are excluded."""
        gov = self._make_governance()
        is_sens, category = gov.is_sensitive("Legal Matter", "Attorney-client privileged communication")
        assert is_sens is True
        assert category == "legal"

    def test_safeguard_2_sensitive_exclusion_medical(self):
        """Safeguard #2: Medical emails are excluded."""
        gov = self._make_governance()
        is_sens, category = gov.is_sensitive("Health Update", "Doctor appointment scheduled")
        assert is_sens is True
        assert category == "medical"

    def test_safeguard_2_non_sensitive_passes(self):
        """Safeguard #2: Normal work emails pass through."""
        gov = self._make_governance()
        is_sens, _ = gov.is_sensitive("SSO Deployment", "We will deploy SSO by Friday")
        assert is_sens is False

    def test_safeguard_3_opt_out(self):
        """Safeguard #3: Opted-out users are excluded."""
        gov = self._make_governance()
        assert gov.is_opted_out("raj@acme.com") is False
        gov.opt_out("raj@acme.com")
        assert gov.is_opted_out("raj@acme.com") is True
        gov.opt_in("raj@acme.com")
        assert gov.is_opted_out("raj@acme.com") is False

    def test_safeguard_4_private_marking(self):
        """Safeguard #4: Signals can be marked private."""
        gov = self._make_governance()
        gov.mark_private("signal-123")
        assert "signal-123" in gov._private_signals

    def test_safeguard_5_retention_expiry(self):
        """Safeguard #5: 90-day retention is enforced."""
        gov = self._make_governance()
        expiry = gov.compute_retention_expiry()
        assert (expiry - datetime.now(timezone.utc)).days <= 91  # ~90 days

        # Test expired signal
        from maestro_oem.workplace_signal_fusion import WorkplaceSignal, SignalSource, SignalCategory
        old_signal = WorkplaceSignal(
            signal_id="old-1",
            source=SignalSource.EMAIL,
            category=SignalCategory.COMMITMENT,
            sender="raj@acme.com",
            recipients=[],
            subject="Old",
            body_preview="",
            timestamp=datetime.now(timezone.utc) - timedelta(days=100),
            company_domain="acme.com",
            retention_expires=datetime.now(timezone.utc) - timedelta(days=10),  # expired 10 days ago
        )
        assert gov.is_expired(old_signal) is True

    def test_safeguard_6_access_control(self):
        """Safeguard #6: Employees see only their own data."""
        gov = self._make_governance()
        from maestro_oem.workplace_signal_fusion import WorkplaceSignal, SignalSource, SignalCategory
        signal = WorkplaceSignal(
            signal_id="test-1",
            source=SignalSource.EMAIL,
            category=SignalCategory.COMMITMENT,
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="Test",
            body_preview="",
            timestamp=datetime.now(timezone.utc),
            company_domain="acme.com",
        )
        # Sender can access
        assert gov.can_access("raj@acme.com", signal) is True
        # Recipient can access
        assert gov.can_access("sam@acme.com", signal) is True
        # Non-participant cannot access
        assert gov.can_access("other@acme.com", signal) is False
        # Admin can access
        assert gov.can_access("admin@acme.com", signal) is True

    def test_safeguard_7_audit_log(self):
        """Safeguard #7: All actions are logged for compliance."""
        gov = self._make_governance()
        gov.opt_out("raj@acme.com")
        gov._log_audit("ingest", "raj@acme.com", signal_id="sig-1")
        gov.log_access("sam@acme.com", "sig-1")

        log = gov.get_audit_log()
        assert len(log) >= 3
        actions = [e["action"] for e in log]
        assert "opt_out" in actions
        assert "ingest" in actions
        assert "access" in actions


class TestWorkplaceSignalFusion:
    """Phase 17: Workplace Signal Fusion engine."""

    def _make_fusion(self, domain="acme.com"):
        from maestro_oem.workplace_signal_fusion import DataGovernanceLayer, WorkplaceSignalFusion
        gov = DataGovernanceLayer(company_domain=domain)
        return WorkplaceSignalFusion(gov), gov

    def test_email_commitment_detection(self):
        """Commitments are detected from work emails."""
        fusion, gov = self._make_fusion()
        signals = fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="SSO Deployment",
            body="We will deploy SSO by Friday.",
        )
        assert len(signals) >= 1
        from maestro_oem.workplace_signal_fusion import SignalCategory
        commitments = [s for s in signals if s.category == SignalCategory.COMMITMENT]
        assert len(commitments) >= 1

    def test_non_company_domain_blocked(self):
        """Non-company-domain emails are blocked (Safeguard #1)."""
        fusion, gov = self._make_fusion("acme.com")
        signals = fusion.process_email(
            sender="raj@gmail.com",  # not company domain
            recipients=["sam@acme.com"],
            subject="Test",
            body="We will deploy SSO.",
        )
        assert len(signals) == 0

    def test_sensitive_email_blocked(self):
        """Sensitive emails are blocked (Safeguard #2)."""
        fusion, gov = self._make_fusion()
        signals = fusion.process_email(
            sender="hr@acme.com",
            recipients=["raj@acme.com"],
            subject="HR: Benefits enrollment",
            body="Your benefits are changing.",
        )
        assert len(signals) == 0

    def test_opted_out_user_blocked(self):
        """Opted-out users are blocked (Safeguard #3)."""
        fusion, gov = self._make_fusion()
        gov.opt_out("raj@acme.com")
        signals = fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="SSO",
            body="We will deploy SSO.",
        )
        assert len(signals) == 0

    def test_slack_signal_detection(self):
        """Signals are detected from Slack messages."""
        fusion, gov = self._make_fusion()
        signals = fusion.process_slack(
            sender="raj@acme.com",
            channel="#engineering",
            message="We decided to ship the API by next Friday. Action item: Sam to review.",
        )
        assert len(signals) >= 1

    def test_decision_detection(self):
        """Decisions are detected from communication."""
        fusion, gov = self._make_fusion()
        signals = fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="Meeting follow-up",
            body="We decided to go with the phased rollout approach.",
        )
        from maestro_oem.workplace_signal_fusion import SignalCategory
        decisions = [s for s in signals if s.category == SignalCategory.DECISION]
        assert len(decisions) >= 1

    def test_risk_detection(self):
        """Risks are detected from communication."""
        fusion, gov = self._make_fusion()
        signals = fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="Project update",
            body="There is a risk the SSO deployment will be delayed.",
        )
        from maestro_oem.workplace_signal_fusion import SignalCategory
        risks = [s for s in signals if s.category == SignalCategory.RISK]
        assert len(risks) >= 1

    def test_retention_applied(self):
        """All signals get 90-day retention expiry."""
        fusion, gov = self._make_fusion()
        signals = fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="SSO",
            body="We will deploy SSO by Friday.",
        )
        for sig in signals:
            assert sig.retention_expires is not None
            days_left = (sig.retention_expires - datetime.now(timezone.utc)).days
            assert 89 <= days_left <= 91  # ~90 days

    def test_audit_log_on_ingest(self):
        """Ingest is logged in the audit log (Safeguard #7)."""
        fusion, gov = self._make_fusion()
        fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="SSO",
            body="We will deploy SSO.",
        )
        log = gov.get_audit_log()
        actions = [e["action"] for e in log]
        assert "ingest" in actions

    def test_access_control_on_get_signals(self):
        """get_signals respects access control (Safeguard #6)."""
        fusion, gov = self._make_fusion()
        fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="SSO",
            body="We will deploy SSO.",
        )
        # Raj (sender) can see
        raj_signals = fusion.get_signals("raj@acme.com")
        assert len(raj_signals) >= 1
        # Sam (recipient) can see
        sam_signals = fusion.get_signals("sam@acme.com")
        assert len(sam_signals) >= 1
        # Other cannot see
        other_signals = fusion.get_signals("other@acme.com")
        assert len(other_signals) == 0

    def test_cleanup_expired(self):
        """Expired signals are cleaned up (Safeguard #5)."""
        fusion, gov = self._make_fusion()
        fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="SSO",
            body="We will deploy SSO.",
        )
        # Manually expire all signals
        for sig in gov._signals.values():
            sig.retention_expires = datetime.now(timezone.utc) - timedelta(days=1)
        deleted = fusion.cleanup_expired()
        assert deleted >= 1
        assert len(gov._signals) == 0

    def test_individual_deployment_forbidden(self):
        """Individual deployment mode is forbidden for this feature."""
        from maestro_oem.workplace_signal_fusion import WorkplaceSignalFusion, DataGovernanceLayer, DeploymentMode
        gov = DataGovernanceLayer(company_domain="acme.com")
        fusion = WorkplaceSignalFusion(gov)
        fusion._deployment_mode = DeploymentMode.INDIVIDUAL
        signals = fusion.process_email(
            sender="raj@acme.com",
            recipients=["sam@acme.com"],
            subject="Test",
            body="We will deploy.",
        )
        assert len(signals) == 0  # forbidden


class TestPhase17L0NoRegression:
    """Phase 17 must not regress the L0 substrate."""

    def test_situation_snapshot_27_fields(self):
        from maestro_oem.situation import Situation
        import dataclasses
        assert len(dataclasses.fields(Situation)) == 27

    def test_outcome_ledger_functional(self):
        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

    def test_classifier_new_types(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO by Q4.") == "tentative"
