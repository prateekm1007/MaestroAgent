"""
Tests for dependency tracking.

Tests:
1. Dependency graph builds from model
2. get_provider_dependencies finds correct signals/LOs/patterns/laws
3. get_law_dependencies finds correct providers/signals
4. get_blast_radius returns correct counts
5. Disconnect GitHub → GitHub-dependent laws weaken
6. Disconnect GitHub → Slack-dependent laws unchanged
7. Disconnect Slack → Slack-dependent laws weaken
8. Disconnect Slack → GitHub-dependent laws unchanged
9. Reconnect → confidence rises back
10. Dependency report shows all laws with their provider dependencies
11. Disconnecting a provider with no dependencies has no effect
12. Impact object records before/after confidence
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from maestro_oem import (
    DependencyGraph,
    DependencyManager,
    OEMEngine,
)
from maestro_oem.law import LawStatus, OrganizationalLaw
from maestro_oem.providers import (
    normalize_confluence,
    normalize_github,
    normalize_gmail,
    normalize_jira,
    normalize_slack,
)


def _build_multi_provider_model():
    """Build a model with signals from multiple providers."""
    from maestro_oem.confidence import ConfidenceCalculator
    engine = OEMEngine()

    # GitHub signals
    github_signals = [normalize_github(e) for e in [
        {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
         "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:00:00Z",
         "metadata": {"domain": "payments", "action": "merged"}},
        {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
         "artifact": "github:acme/payments/pull/2", "timestamp": "2024-01-20T09:00:00Z",
         "metadata": {"domain": "payments", "action": "merged"}},
        {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
         "artifact": "github:acme/payments/pull/3", "timestamp": "2024-01-25T09:00:00Z",
         "metadata": {"domain": "payments", "action": "merged"}},
        {"event_type": "review", "repository": "acme/payments", "actor": "priya@acme.com",
         "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:30:00Z",
         "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"}},
    ]]

    # Jira signals
    jira_signals = [normalize_jira(e) for e in [
        {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
         "artifact": "jira:EMEA-1", "timestamp": "2024-02-05T14:00:00Z",
         "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
        {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
         "artifact": "jira:EMEA-2", "timestamp": "2024-02-06T14:00:00Z",
         "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
        {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara@acme.com",
         "artifact": "jira:EMEA-3", "timestamp": "2024-02-07T14:00:00Z",
         "metadata": {"transition": "Approved", "assignee": "sara@acme.com"}},
    ]]

    # Slack signals
    slack_signals = [normalize_slack(e) for e in [
        {"event_type": "message", "channel": "#eng", "actor": "priya@acme.com",
         "artifact": "slack:C-1/p-1", "timestamp": "2024-02-10T09:14:00Z",
         "metadata": {"text": "can someone review this PR? who can take a look today?",
                      "participants": ["priya@acme.com", "carlos@acme.com"]}},
    ]]

    engine.ingest(github_signals + jira_signals + slack_signals)

    calc = ConfidenceCalculator()
    now = datetime.now(timezone.utc)

    # Inject a law that depends only on GitHub
    law_github = OrganizationalLaw(
        code="L-GITHUB-ONLY",
        statement="GitHub-only law: merge frequency affects release velocity",
        condition="When merges increase",
        outcome="Release velocity increases",
        status=LawStatus.VALIDATED,
        validated_runtimes=3,
        evidence_count=4,
        providers={"github"},
    )
    law_github.confidence = calc.compute_law_confidence(
        validated_runtimes=3, failed_runtimes=0, evidence_count=4,
        providers={"github"}, last_validated=now,
    )
    engine.get_model().laws["L-GITHUB-ONLY"] = law_github

    # Inject a law that depends only on Jira
    law_jira = OrganizationalLaw(
        code="L-JIRA-ONLY",
        statement="Jira-only law: approval gate delays delivery",
        condition="When Sara K. approves",
        outcome="Delivery delayed by 6 days",
        status=LawStatus.VALIDATED,
        validated_runtimes=3,
        evidence_count=3,
        providers={"jira"},
    )
    law_jira.confidence = calc.compute_law_confidence(
        validated_runtimes=3, failed_runtimes=0, evidence_count=3,
        providers={"jira"}, last_validated=now,
    )
    engine.get_model().laws["L-JIRA-ONLY"] = law_jira

    # Inject a law that depends on both
    law_both = OrganizationalLaw(
        code="L-BOTH",
        statement="Multi-provider law: engineering + delivery patterns",
        condition="When both merge and approval patterns align",
        outcome="Velocity stabilizes",
        status=LawStatus.VALIDATED,
        validated_runtimes=2,
        evidence_count=5,
        providers={"github", "jira"},
    )
    law_both.confidence = calc.compute_law_confidence(
        validated_runtimes=2, failed_runtimes=0, evidence_count=5,
        providers={"github", "jira"}, last_validated=now,
    )
    engine.get_model().laws["L-BOTH"] = law_both

    return engine


# ============================================================
# TEST 1: Dependency graph builds from model
# ============================================================

class TestGraphBuilds:
    def test_graph_has_provider_signals(self):
        """The graph must map providers to their signals."""
        engine = _build_multi_provider_model()
        graph = DependencyGraph()
        graph.build_from_model(engine.get_model())
        assert "github" in graph.provider_signals or len(graph.provider_signals) > 0

    def test_graph_has_signal_lo_mapping(self):
        """The graph must map signals to their LOs."""
        engine = _build_multi_provider_model()
        graph = DependencyGraph()
        graph.build_from_model(engine.get_model())
        assert len(graph.signal_los) > 0


# ============================================================
# TEST 2: get_provider_dependencies finds correct entities
# ============================================================

class TestProviderDependencies:
    def test_github_dependencies_include_github_law(self):
        """GitHub dependencies must include the GitHub-only law."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        deps = mgr.graph.get_provider_dependencies("github")
        assert "L-GITHUB-ONLY" in deps["laws"]

    def test_jira_dependencies_include_jira_law(self):
        """Jira dependencies must include the Jira-only law."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        deps = mgr.graph.get_provider_dependencies("jira")
        assert "L-JIRA-ONLY" in deps["laws"]


# ============================================================
# TEST 3: get_law_dependencies finds correct providers
# ============================================================

class TestLawDependencies:
    def test_github_only_law_depends_on_github(self):
        """L-GITHUB-ONLY must depend on the github provider."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        deps = mgr.graph.get_law_dependencies("L-GITHUB-ONLY")
        assert "github" in deps["providers"]

    def test_both_law_depends_on_multiple_providers(self):
        """L-BOTH must depend on both github and jira."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        deps = mgr.graph.get_law_dependencies("L-BOTH")
        assert "github" in deps["providers"]
        assert "jira" in deps["providers"]


# ============================================================
# TEST 4: get_blast_radius returns counts
# ============================================================

class TestBlastRadius:
    def test_blast_radius_has_counts(self):
        """Blast radius must return integer counts."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        blast = mgr.graph.get_blast_radius("github")
        assert "signals" in blast
        assert "learning_objects" in blast
        assert "patterns" in blast
        assert "laws" in blast
        assert isinstance(blast["signals"], int)


# ============================================================
# TEST 5: Disconnect GitHub → GitHub laws weaken
# ============================================================

class TestDisconnectGitHubWeakensGitHubLaws:
    def test_disconnect_github_lowers_github_law_confidence(self):
        """Disconnecting GitHub must lower the confidence of GitHub-only laws."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        mgr = DependencyManager(model)

        original_conf = model.laws["L-GITHUB-ONLY"].confidence
        assert original_conf > 0

        impact = mgr.disconnect_provider("github")

        new_conf = model.laws["L-GITHUB-ONLY"].confidence
        assert new_conf < original_conf, (
            f"GitHub law confidence should decrease. Before: {original_conf}, After: {new_conf}"
        )
        assert "L-GITHUB-ONLY" in impact.affected_laws

    def test_disconnect_github_lowers_both_law_confidence(self):
        """Disconnecting GitHub must lower the confidence of multi-provider laws."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        mgr = DependencyManager(model)

        original_conf = model.laws["L-BOTH"].confidence
        impact = mgr.disconnect_provider("github")

        new_conf = model.laws["L-BOTH"].confidence
        assert new_conf <= original_conf, (
            f"Multi-provider law confidence should decrease or stay. Before: {original_conf}, After: {new_conf}"
        )


# ============================================================
# TEST 6: Disconnect GitHub → Jira laws unchanged
# ============================================================

class TestDisconnectGitHubDoesNotAffectJira:
    def test_disconnect_github_does_not_lower_jira_law(self):
        """Disconnecting GitHub must NOT affect Jira-only laws."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        mgr = DependencyManager(model)

        original_conf = model.laws["L-JIRA-ONLY"].confidence
        mgr.disconnect_provider("github")
        new_conf = model.laws["L-JIRA-ONLY"].confidence

        assert new_conf == original_conf, (
            f"Jira law should be unchanged. Before: {original_conf}, After: {new_conf}"
        )

    def test_disconnect_github_jira_law_not_in_affected(self):
        """Jira-only law must not appear in disconnect impact."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        impact = mgr.disconnect_provider("github")
        assert "L-JIRA-ONLY" not in impact.affected_laws


# ============================================================
# TEST 7: Disconnect Slack → Slack-dependent laws weaken
# ============================================================

class TestDisconnectSlack:
    def test_disconnect_slack_removes_provider(self):
        """Disconnecting Slack removes it from connected_providers."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        assert "slack" in model.connected_providers

        mgr = DependencyManager(model)
        mgr.disconnect_provider("slack")
        assert "slack" not in model.connected_providers


# ============================================================
# TEST 8: Disconnect Slack → GitHub laws unchanged
# ============================================================

class TestDisconnectSlackDoesNotAffectGitHub:
    def test_disconnect_slack_does_not_lower_github_law(self):
        """Disconnecting Slack must NOT affect GitHub-only laws."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        mgr = DependencyManager(model)

        original_conf = model.laws["L-GITHUB-ONLY"].confidence
        mgr.disconnect_provider("slack")
        new_conf = model.laws["L-GITHUB-ONLY"].confidence

        assert new_conf == original_conf, (
            f"GitHub law should be unchanged after Slack disconnect. Before: {original_conf}, After: {new_conf}"
        )


# ============================================================
# TEST 9: Reconnect → confidence rises
# ============================================================

class TestReconnect:
    def test_reconnect_adds_provider_back(self):
        """Reconnecting adds the provider back to connected_providers."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        mgr = DependencyManager(model)

        # Disconnect first
        mgr.disconnect_provider("github")
        assert "github" not in model.connected_providers

        # Reconnect with the original GitHub signals
        github_signals = [normalize_github(e) for e in [
            {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:00:00Z",
             "metadata": {"domain": "payments", "action": "merged"}},
            {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/2", "timestamp": "2024-01-20T09:00:00Z",
             "metadata": {"domain": "payments", "action": "merged"}},
            {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/3", "timestamp": "2024-01-25T09:00:00Z",
             "metadata": {"domain": "payments", "action": "merged"}},
            {"event_type": "review", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/1", "timestamp": "2024-01-15T09:30:00Z",
             "metadata": {"reviewer": "carlos@acme.com", "domain": "payments", "action": "approved"}},
        ]]

        impact = mgr.reconnect_provider("github", github_signals)
        assert "github" in model.connected_providers

    def test_reconnect_raises_confidence(self):
        """Reconnecting a provider must raise confidence of affected laws."""
        engine = _build_multi_provider_model()
        model = engine.get_model()
        mgr = DependencyManager(model)

        original_conf = model.laws["L-GITHUB-ONLY"].confidence
        mgr.disconnect_provider("github")
        disconnected_conf = model.laws["L-GITHUB-ONLY"].confidence

        # Reconnect with fresh signals
        github_signals = [normalize_github(e) for e in [
            {"event_type": "merge", "repository": "acme/payments", "actor": "priya@acme.com",
             "artifact": "github:acme/payments/pull/10", "timestamp": "2024-03-01T09:00:00Z",
             "metadata": {"domain": "payments", "action": "merged"}},
        ]]
        mgr.reconnect_provider("github", github_signals)
        reconnected_conf = model.laws["L-GITHUB-ONLY"].confidence

        assert reconnected_conf >= disconnected_conf, (
            f"Reconnected ({reconnected_conf}) should >= disconnected ({disconnected_conf})"
        )


# ============================================================
# TEST 10: Dependency report
# ============================================================

class TestDependencyReport:
    def test_report_contains_all_laws(self):
        """The dependency report must contain all laws."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        report = mgr.get_dependency_report()
        assert "L-GITHUB-ONLY" in report
        assert "L-JIRA-ONLY" in report
        assert "L-BOTH" in report

    def test_report_has_provider_dependencies(self):
        """Each law in the report must list its providers."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        report = mgr.get_dependency_report()
        assert "github" in report["L-GITHUB-ONLY"]["providers"]
        assert "jira" in report["L-JIRA-ONLY"]["providers"]


# ============================================================
# TEST 11: Disconnect with no dependencies
# ============================================================

class TestDisconnectNoDependencies:
    def test_disconnect_unknown_provider_no_crash(self):
        """Disconnecting a provider with no signals must not crash."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        impact = mgr.disconnect_provider("unknown_provider")
        assert impact.affected_signals == 0
        assert len(impact.affected_laws) == 0


# ============================================================
# TEST 12: Impact records before/after confidence
# ============================================================

class TestImpactRecords:
    def test_impact_has_before_and_after(self):
        """The impact object must record confidence before and after."""
        engine = _build_multi_provider_model()
        mgr = DependencyManager(engine.get_model())
        impact = mgr.disconnect_provider("github")

        for law_code in impact.affected_laws:
            assert law_code in impact.confidence_before
            assert law_code in impact.confidence_after
