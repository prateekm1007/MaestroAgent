"""Phase 2 — Derived-data deletion propagation test (P22).

When a provider is disconnected, signals from that provider must be removed,
and derived laws/learning_objects that depended ONLY on that provider must
be cleaned up. This prevents stale data from a disconnected provider from
persisting in the OEM.

P22: this test executes the production path (OEMState.disconnect_provider +
real OEMEngine model), not a unit test of a filter in isolation.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _make_signal(
    text: str,
    provider: str = "slack",
    customer: str = "Globex",
    actor: str = "alice@acme.com",
    signal_type: str = "customer_commitment_made",
):
    """Create a test signal with a specific provider."""
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    sig_map = {
        "customer_commitment_made": SignalType.CUSTOMER_COMMITMENT_MADE,
        "message_sent": SignalType.MESSAGE_SENT,
        "pr_opened": SignalType.PR_OPENED,
    }
    provider_map = {
        "slack": SignalProvider.SLACK,
        "github": SignalProvider.GITHUB,
        "jira": SignalProvider.JIRA,
        "gmail": SignalProvider.GMAIL,
        "confluence": SignalProvider.CONFLUENCE,
        "customer": SignalProvider.CUSTOMER,
    }
    return ExecutionSignal(
        type=sig_map.get(signal_type, SignalType.MESSAGE_SENT),
        actor=actor,
        artifact=f"test:{uuid4().hex[:8]}",
        metadata={"customer": customer, "text": text, "body": text},
        provider=provider_map.get(provider, SignalProvider.SLACK),
        timestamp=datetime.now(timezone.utc),
    )


class TestDeletionPropagation:
    """P22: verify derived-data deletion propagation when a provider is disconnected."""

    def test_disconnect_removes_provider_signals(self):
        """Disconnecting a provider removes its signals from oem_state."""
        from maestro_api.oem_state import OEMState
        state = OEMState()
        state.engine = None
        # Manually add signals from two providers
        state.signals = [
            _make_signal("Slack signal 1", provider="slack"),
            _make_signal("Slack signal 2", provider="slack"),
            _make_signal("GitHub signal 1", provider="github"),
        ]
        assert len(state.signals) == 3

        # Disconnect slack
        state.disconnect_provider("slack")

        # Slack signals should be removed
        remaining_providers = {s.provider.value for s in state.signals}
        assert "slack" not in remaining_providers, \
            f"Slack signals not removed after disconnect: {remaining_providers}"
        assert "github" in remaining_providers, \
            f"GitHub signals should remain: {remaining_providers}"
        assert len(state.signals) == 1, \
            f"Should have 1 signal left (github), got {len(state.signals)}"

    def test_disconnect_removes_provider_only_laws(self):
        """Disconnecting a provider removes laws that ONLY had evidence from that provider."""
        from maestro_api.oem_state import OEMState
        from maestro_oem.law import OrganizationalLaw as Law, LawStatus
        from maestro_oem.learning_object import LearningObject, LearningObjectType

        state = OEMState()
        state.engine = None

        # Create a law with evidence ONLY from slack
        slack_only_law = Law(
            law_id=uuid4(),
            code="L-SLACK-ONLY",
            statement="Law from slack only",
            condition="condition",
            outcome="outcome",
            status=LawStatus.VALIDATED,
            signal_ids=[uuid4(), uuid4()],
            providers={"slack"},
            evidence_count=2,
        )

        # Create a law with evidence from BOTH slack + github
        multi_provider_law = Law(
            law_id=uuid4(),
            code="L-MULTI",
            statement="Law from multiple providers",
            condition="condition",
            outcome="outcome",
            status=LawStatus.VALIDATED,
            signal_ids=[uuid4(), uuid4()],
            providers={"slack", "github"},
            evidence_count=2,
        )

        # Add laws to the model
        from maestro_oem.model import ExecutionModel
        model = ExecutionModel()
        model.laws[slack_only_law.code] = slack_only_law
        model.laws[multi_provider_law.code] = multi_provider_law
        state.engine = type("MockEngine", (), {"get_model": lambda self: model})()

        # Disconnect slack
        state.disconnect_provider("slack")

        # Slack-only law should be removed
        assert "L-SLACK-ONLY" not in model.laws, \
            "Slack-only law should be removed when slack is disconnected"
        # Multi-provider law should remain
        assert "L-MULTI" in model.laws, \
            "Multi-provider law should remain (still has github evidence)"

    def test_disconnect_removes_provider_only_learning_objects(self):
        """Disconnecting a provider removes LOs that ONLY had evidence from that provider."""
        from maestro_api.oem_state import OEMState
        from maestro_oem.learning_object import LearningObject, LearningObjectType

        state = OEMState()
        state.engine = None

        # Create LOs
        slack_only_lo = LearningObject(
            lo_id=uuid4(),
            title="Slack-only LO",
            description="LO from slack only",
            type=LearningObjectType.BOTTLENECK,
            signal_ids=[uuid4()],
            providers={"slack"},
            evidence_count=1,
        )
        multi_lo = LearningObject(
            lo_id=uuid4(),
            title="Multi-provider LO",
            description="LO from multiple providers",
            type=LearningObjectType.BOTTLENECK,
            signal_ids=[uuid4()],
            providers={"slack", "github"},
            evidence_count=2,
        )

        from maestro_oem.model import ExecutionModel
        model = ExecutionModel()
        model.learning_objects[slack_only_lo.lo_id] = slack_only_lo
        model.learning_objects[multi_lo.lo_id] = multi_lo
        state.engine = type("MockEngine", (), {"get_model": lambda self: model})()

        # Disconnect slack
        state.disconnect_provider("slack")

        # Slack-only LO should be removed
        remaining_lo_ids = {lo_id for lo_id in model.learning_objects}
        assert slack_only_lo.lo_id not in remaining_lo_ids, \
            "Slack-only LO should be removed when slack is disconnected"
        assert multi_lo.lo_id in remaining_lo_ids, \
            "Multi-provider LO should remain (still has github evidence)"

    def test_disconnect_preserves_other_providers_data(self):
        """Disconnecting one provider doesn't affect data from other providers."""
        from maestro_api.oem_state import OEMState

        state = OEMState()
        state.engine = None
        state.signals = [
            _make_signal("GitHub 1", provider="github"),
            _make_signal("GitHub 2", provider="github"),
            _make_signal("Jira 1", provider="jira"),
        ]

        # Disconnect github
        state.disconnect_provider("github")

        # Only jira should remain
        remaining_providers = {s.provider.value for s in state.signals}
        assert remaining_providers == {"jira"}, \
            f"Only jira should remain, got {remaining_providers}"
        assert len(state.signals) == 1
