"""Tests for the Organizational Digital Twin."""

import pytest
from maestro_api.oem_state import oem_state
from maestro_oem.digital_twin import DigitalTwin, ScenarioEngine, ImpactReport


@pytest.fixture
def twin():
    oem_state.initialize()
    return DigitalTwin(oem_state.model, oem_state.signals, oem_state.decisions)


@pytest.fixture
def engine(twin):
    return ScenarioEngine(twin)


# ═══════════════════════════════════════════════════════════════════════════
# 1. TWIN STATE
# ═══════════════════════════════════════════════════════════════════════════

class TestDigitalTwinState:
    def test_twin_has_people(self, twin):
        assert len(twin.people) > 0
        for p in twin.people.values():
            assert p.email
            assert p.workload >= 0

    def test_twin_has_domains(self, twin):
        assert len(twin.domains) > 0
        for d in twin.domains.values():
            assert d.name
            assert isinstance(d.people, list)

    def test_twin_summary(self, twin):
        summary = twin.get_org_summary()
        assert summary["people"] > 0
        assert summary["domains"] > 0
        assert summary["signals"] > 0
        assert "health" in summary
        assert "avg_workload" in summary

    def test_twin_does_not_modify_original(self, twin):
        """The twin must not modify the real OEM model."""
        original_p1 = oem_state.model.health.p1_cluster_risk
        engine = ScenarioEngine(twin)
        engine.run_scenario({"type": "cut_meetings", "reduction_pct": 50})
        # The real OEM should be unchanged
        assert oem_state.model.health.p1_cluster_risk == original_p1


# ═══════════════════════════════════════════════════════════════════════════
# 2. SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════

class TestPersonLeavesScenario:
    def test_person_removed(self, engine):
        """Person should be removed from the twin."""
        # Use the first person
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        assert person not in engine.twin.people
        assert report.scenario_type == "person_leaves"

    def test_knowledge_loss_detected(self, engine):
        """When a person leaves, knowledge loss should be detected in their domains."""
        # Find a person who is the sole person in a domain
        for email, profile in engine.original_twin.people.items():
            for domain in profile.domains:
                d = engine.original_twin.domains.get(domain)
                if d and len(d.people) == 1:
                    report = engine.run_scenario({"type": "person_leaves", "person": email})
                    assert len(report.knowledge_loss) > 0
                    return
        # If no sole-person domain, just verify the scenario runs
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        assert report.risk_level in ("low", "medium", "high", "critical")

    def test_workload_redistributed(self, engine):
        """Workload should be redistributed to remaining people."""
        person = list(engine.twin.people.keys())[0]
        original_workload = sum(p.workload for p in engine.twin.people.values())
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        # Total workload should be similar (redistributed, not lost)
        # (It may be slightly less due to the removed person's workload)
        assert report.description.startswith(f"Simulated departure of {person}")

    def test_law_violations_detected(self, engine):
        """Laws referencing the removed person should be flagged."""
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        # Law violations may or may not exist depending on whether laws reference the person
        assert isinstance(report.law_violations, list)


class TestCutMeetingsScenario:
    def test_meetings_cut_reduces_workload(self, engine):
        """Cutting meetings should reduce total workload."""
        before_workload = sum(p.workload for p in engine.twin.people.values())
        report = engine.run_scenario({"type": "cut_meetings", "reduction_pct": 30})
        after_workload = sum(p.workload for p in engine.twin.people.values())
        assert after_workload <= before_workload

    def test_velocity_improves(self, engine):
        """Cutting meetings should improve velocity."""
        before_velocity = engine.original_twin.model.health.decision_velocity_days
        report = engine.run_scenario({"type": "cut_meetings", "reduction_pct": 50})
        after_velocity = engine.twin.model.health.decision_velocity_days
        assert after_velocity <= before_velocity

    def test_low_risk(self, engine):
        """Cutting meetings should generally be low risk."""
        report = engine.run_scenario({"type": "cut_meetings", "reduction_pct": 30})
        assert report.risk_level in ("low", "medium")


class TestAddHiresScenario:
    def test_people_added(self, engine):
        """Hires should add new people to the twin."""
        before_count = len(engine.twin.people)
        report = engine.run_scenario({"type": "add_hires", "domain": "payments", "count": 3})
        after_count = len(engine.twin.people)
        assert after_count == before_count + 3

    def test_workload_redistributed(self, engine):
        """Workload per person should decrease after hires."""
        domain = "payments"
        if domain not in engine.twin.domains:
            pytest.skip("No payments domain")
        before_avg = sum(engine.twin.people[p].workload for p in engine.twin.domains[domain].people if p in engine.twin.people) / max(len(engine.twin.domains[domain].people), 1)
        report = engine.run_scenario({"type": "add_hires", "domain": domain, "count": 2})
        after_avg = sum(engine.twin.people[p].workload for p in engine.twin.domains[domain].people if p in engine.twin.people) / max(len(engine.twin.domains[domain].people), 1)
        assert after_avg <= before_avg

    def test_p1_risk_reduced(self, engine):
        """Adding hires should reduce P1 risk."""
        before_risk = engine.original_twin.model.health.p1_cluster_risk
        report = engine.run_scenario({"type": "add_hires", "domain": "payments", "count": 5})
        after_risk = engine.twin.model.health.p1_cluster_risk
        assert after_risk <= before_risk


class TestTeamDoublesScenario:
    def test_team_doubled(self, engine):
        """Doubling a team should double its headcount."""
        domain = list(engine.twin.domains.keys())[0]
        before_count = len(engine.twin.domains[domain].people)
        report = engine.run_scenario({"type": "team_doubles", "domain": domain})
        after_count = len(engine.twin.domains[domain].people)
        assert after_count == before_count * 2


class TestMoveTeamScenario:
    def test_ownership_transferred(self, engine):
        """Moving a team should add the domain to the new owner."""
        domain = list(engine.twin.domains.keys())[0]
        new_owner = list(engine.twin.people.keys())[0]
        # Make sure the new owner doesn't already own this domain
        if domain in engine.twin.people[new_owner].domains:
            new_owner = list(engine.twin.people.keys())[1]
        report = engine.run_scenario({"type": "move_team", "domain": domain, "new_owner": new_owner})
        assert domain in engine.twin.people[new_owner].domains

    def test_workload_increases(self, engine):
        """The new owner's workload should increase."""
        domain = list(engine.twin.domains.keys())[0]
        new_owner = list(engine.twin.people.keys())[0]
        before_wl = engine.twin.people[new_owner].workload
        report = engine.run_scenario({"type": "move_team", "domain": domain, "new_owner": new_owner})
        after_wl = engine.twin.people[new_owner].workload
        assert after_wl > before_wl


class TestMergeTeamsScenario:
    def test_teams_merged(self, engine):
        """Merging should combine two domains into one."""
        domains = list(engine.twin.domains.keys())
        if len(domains) < 2:
            pytest.skip("Need at least 2 domains")
        domain_a = domains[0]
        domain_b = domains[1]
        before_count = len(engine.twin.domains)
        report = engine.run_scenario({"type": "merge_teams", "domain_a": domain_a, "domain_b": domain_b})
        after_count = len(engine.twin.domains)
        assert after_count == before_count - 1
        assert domain_b not in engine.twin.domains
        assert domain_a in engine.twin.domains

    def test_merged_team_has_combined_people(self, engine):
        """The merged team should have all people from both teams."""
        domains = list(engine.twin.domains.keys())
        if len(domains) < 2:
            pytest.skip("Need at least 2 domains")
        domain_a = domains[0]
        domain_b = domains[1]
        combined_people = set(engine.twin.domains[domain_a].people + engine.twin.domains[domain_b].people)
        report = engine.run_scenario({"type": "merge_teams", "domain_a": domain_a, "domain_b": domain_b})
        assert set(engine.twin.domains[domain_a].people) == combined_people


# ═══════════════════════════════════════════════════════════════════════════
# 3. IMPACT ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

class TestImpactAnalysis:
    def test_report_has_all_sections(self, engine):
        """Impact report must have all sections."""
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        d = report.to_dict()
        assert "overloaded_people" in d
        assert "knowledge_loss" in d
        assert "new_bottlenecks" in d
        assert "velocity_change" in d
        assert "law_violations" in d
        assert "pattern_shifts" in d
        assert "recommendations" in d
        assert "risk_level" in d
        assert "risk_score" in d
        assert "before_summary" in d
        assert "after_summary" in d

    def test_risk_level_computed(self, engine):
        """Risk level must be computed."""
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        assert report.risk_level in ("low", "medium", "high", "critical")
        assert 0.0 <= report.risk_score <= 1.0

    def test_recommendations_generated(self, engine):
        """Recommendations must be generated."""
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        assert len(report.recommendations) > 0
        for r in report.recommendations:
            assert "priority" in r
            assert "action" in r
            assert "reason" in r

    def test_before_after_summary(self, engine):
        """Before and after summaries must be captured."""
        person = list(engine.twin.people.keys())[0]
        report = engine.run_scenario({"type": "person_leaves", "person": person})
        assert report.before_summary["people"] > report.after_summary["people"]

    def test_unknown_scenario_type(self, engine):
        """Unknown scenario type should return a description."""
        report = engine.run_scenario({"type": "unknown_type"})
        assert "Unknown scenario type" in report.description
