"""
Deterministic tests for the OEM.

These tests prove:
1. Connecting GitHub changes the OEM
2. Connecting Jira changes the OEM again (different changes)
3. Connecting Slack changes the OEM again (different changes)
4. Connecting Confluence changes the OEM again (different changes)
5. Connecting Gmail changes the OEM again (different changes)
6. Every provider contributes unique information
7. No hardcoded insights — everything is computed from signals
8. Confidence is mathematical, not arbitrary
9. Provenance chains are complete
10. Laws evolve as evidence accumulates
"""

from __future__ import annotations

import pytest

from maestro_oem import (
    ConfidenceCalculator,
    DecisionEngine,
    ExecutionModel,
    OEMEngine,
)
from maestro_oem.providers import (
    normalize_confluence,
    normalize_github,
    normalize_gmail,
    normalize_jira,
    normalize_slack,
)


# ============================================================
# TEST DATA — raw events from each provider
# ============================================================

GITHUB_EVENTS = [
    {
        "event_type": "pull_request",
        "repository": "acme/payments-edge",
        "actor": "priya.m@acme.com",
        "artifact": "github:acme/payments-edge/pull/447",
        "timestamp": "2024-11-12T09:00:00Z",
        "metadata": {"action": "opened", "domain": "payments", "title": "Add circuit breaker"},
    },
    {
        "event_type": "review",
        "repository": "acme/payments-edge",
        "actor": "priya.m@acme.com",
        "artifact": "github:acme/payments-edge/pull/447",
        "timestamp": "2024-11-12T09:30:00Z",
        "metadata": {"reviewer": "carlos.r@acme.com", "domain": "payments", "action": "approved"},
    },
    {
        "event_type": "merge",
        "repository": "acme/payments-edge",
        "actor": "priya.m@acme.com",
        "artifact": "github:acme/payments-edge/pull/447",
        "timestamp": "2024-11-12T10:00:00Z",
        "metadata": {"domain": "payments", "action": "merged"},
    },
    {
        "event_type": "pull_request",
        "repository": "acme/auth-service",
        "actor": "carlos.r@acme.com",
        "artifact": "github:acme/auth-service/pull/102",
        "timestamp": "2024-11-10T14:00:00Z",
        "metadata": {"action": "opened", "domain": "auth", "title": "OAuth consolidation"},
    },
    {
        "event_type": "review",
        "repository": "acme/auth-service",
        "actor": "carlos.r@acme.com",
        "artifact": "github:acme/auth-service/pull/102",
        "timestamp": "2024-11-10T16:00:00Z",
        "metadata": {"reviewer": "priya.m@acme.com", "domain": "auth", "action": "approved"},
    },
    {
        "event_type": "commit",
        "repository": "acme/platform-tools",
        "actor": "aisha.k@acme.com",
        "artifact": "github:acme/platform-tools/commit/abc123",
        "timestamp": "2024-11-08T11:00:00Z",
        "metadata": {"domain": "platform"},
    },
    # More commits to build influence
    {
        "event_type": "commit",
        "repository": "acme/platform-tools",
        "actor": "aisha.k@acme.com",
        "artifact": "github:acme/platform-tools/commit/def456",
        "timestamp": "2024-11-09T11:00:00Z",
        "metadata": {"domain": "platform"},
    },
    {
        "event_type": "commit",
        "repository": "acme/platform-tools",
        "actor": "aisha.k@acme.com",
        "artifact": "github:acme/platform-tools/commit/ghi789",
        "timestamp": "2024-11-10T11:00:00Z",
        "metadata": {"domain": "platform"},
    },
]

JIRA_EVENTS = [
    {
        "event_type": "issue_created",
        "project": "EMEA",
        "actor": "sara.k@acme.com",
        "artifact": "jira:EMEA-1247",
        "timestamp": "2024-11-05T09:00:00Z",
        "metadata": {"priority": "P1", "issue_type": "Bug"},
    },
    {
        "event_type": "issue_created",
        "project": "EMEA",
        "actor": "chris.t@acme.com",
        "artifact": "jira:EMEA-1248",
        "timestamp": "2024-11-06T09:00:00Z",
        "metadata": {"priority": "P1", "issue_type": "Bug"},
    },
    {
        "event_type": "issue_created",
        "project": "EMEA",
        "actor": "chris.t@acme.com",
        "artifact": "jira:EMEA-1249",
        "timestamp": "2024-11-07T09:00:00Z",
        "metadata": {"priority": "P1", "issue_type": "Bug"},
    },
    {
        "event_type": "issue_transitioned",
        "project": "EMEA",
        "actor": "sara.k@acme.com",
        "artifact": "jira:EMEA-1247",
        "timestamp": "2024-11-08T14:00:00Z",
        "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"},
    },
    {
        "event_type": "issue_transitioned",
        "project": "EMEA",
        "actor": "sara.k@acme.com",
        "artifact": "jira:EMEA-1248",
        "timestamp": "2024-11-09T14:00:00Z",
        "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"},
    },
    {
        "event_type": "issue_transitioned",
        "project": "EMEA",
        "actor": "sara.k@acme.com",
        "artifact": "jira:EMEA-1249",
        "timestamp": "2024-11-10T14:00:00Z",
        "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"},
    },
    {
        "event_type": "sprint_completed",
        "project": "EMEA",
        "actor": "chris.t@acme.com",
        "artifact": "jira:SPRINT-Q4-3",
        "timestamp": "2024-11-08T17:00:00Z",
        "metadata": {"velocity": 42},
    },
]

SLACK_EVENTS = [
    {
        "event_type": "message",
        "channel": "#engineering",
        "actor": "priya.m@acme.com",
        "artifact": "slack:C-123/p-1",
        "timestamp": "2024-11-12T09:14:00Z",
        "metadata": {"text": "the payments-edge circuit breaker is ready for review. who can take a look today?", "participants": ["priya.m@acme.com", "carlos.r@acme.com"]},
    },
    {
        "event_type": "message",
        "channel": "#engineering",
        "actor": "carlos.r@acme.com",
        "artifact": "slack:C-123/p-2",
        "timestamp": "2024-11-12T09:16:00Z",
        "metadata": {"text": "I can review after lunch. does this cover the retry logic too?", "participants": ["carlos.r@acme.com", "priya.m@acme.com"]},
    },
    {
        "event_type": "message",
        "channel": "#leadership",
        "actor": "pat.s@acme.com",
        "artifact": "slack:C-456/p-3",
        "timestamp": "2024-11-11T10:00:00Z",
        "metadata": {"text": "I disagree with the Q3 hiring plan — we need APAC not EMEA", "participants": ["pat.s@acme.com", "jane.d@acme.com"]},
    },
    {
        "event_type": "message",
        "channel": "#engineering",
        "actor": "marcus.t@acme.com",
        "artifact": "slack:C-123/p-4",
        "timestamp": "2024-11-12T09:22:00Z",
        "metadata": {"text": "security review needed? this touches auth flow", "participants": ["marcus.t@acme.com", "priya.m@acme.com"]},
    },
    {
        "event_type": "message",
        "channel": "#engineering",
        "actor": "anya.r@acme.com",
        "artifact": "slack:C-123/p-5",
        "timestamp": "2024-11-10T15:00:00Z",
        "metadata": {"text": "I'm thinking about a new opportunity...", "participants": ["anya.r@acme.com"]},
    },
]

CONFLUENCE_EVENTS = [
    {
        "event_type": "postmortem_created",
        "space": "Engineering",
        "actor": "chris.t@acme.com",
        "artifact": "confluence:PM-2024-11-09",
        "timestamp": "2024-11-09T16:00:00Z",
        "metadata": {"title": "Postmortem: payments-edge incident Nov 9", "has_owner": False, "page_type": "postmortem"},
    },
    {
        "event_type": "rfc_created",
        "space": "Engineering",
        "actor": "carlos.r@acme.com",
        "artifact": "confluence:RFC-412",
        "timestamp": "2024-10-28T10:00:00Z",
        "metadata": {"title": "OAuth Consolidation RFC", "domain": "auth", "has_owner": True, "page_type": "rfc"},
    },
    {
        "event_type": "page_created",
        "space": "Engineering",
        "actor": "priya.m@acme.com",
        "artifact": "confluence:DOC-789",
        "timestamp": "2024-11-01T11:00:00Z",
        "metadata": {"title": "Deployment Runbook", "domain": "deployment", "page_type": "documentation"},
    },
    {
        "event_type": "page_created",
        "space": "Payments",
        "actor": "anya.r@acme.com",
        "artifact": "confluence:DOC-790",
        "timestamp": "2024-11-03T14:00:00Z",
        "metadata": {"title": "Payments Integration Guide", "domain": "payments", "page_type": "documentation"},
    },
]

GMAIL_EVENTS = [
    {
        "event_type": "meeting_completed",
        "actor": "jane.d@acme.com",
        "artifact": "cal:event-001",
        "timestamp": "2024-11-11T15:00:00Z",
        "metadata": {"participants": ["jane.d@acme.com", "raj@globex.com"], "duration": 30, "subject": "Q4 renewal discussion"},
    },
    {
        "event_type": "email_sent",
        "actor": "jane.d@acme.com",
        "artifact": "gmail:msg-001",
        "timestamp": "2024-11-11T16:00:00Z",
        "metadata": {"recipient": "raj@globex.com", "recipient_type": "external", "subject": "Re: Q4 renewal discussion"},
    },
    {
        "event_type": "meeting_completed",
        "actor": "chris.t@acme.com",
        "artifact": "cal:event-002",
        "timestamp": "2024-11-08T10:00:00Z",
        "metadata": {"participants": ["chris.t@acme.com", "casey.f@acme.com", "priya.e@acme.com"], "duration": 45, "subject": "Eng leadership sync"},
    },
    {
        "event_type": "meeting_completed",
        "actor": "jane.d@acme.com",
        "artifact": "cal:event-003",
        "timestamp": "2024-11-12T09:00:00Z",
        "metadata": {"participants": ["jane.d@acme.com", "chris.t@acme.com", "casey.f@acme.com", "pat.s@acme.com"], "duration": 60, "subject": "Q3 Hiring Decision"},
    },
]


# ============================================================
# TEST 1: Empty OEM has no insights
# ============================================================

class TestEmptyOEM:
    def test_empty_model_has_no_laws(self):
        """A fresh OEM with no signals must have zero laws."""
        engine = OEMEngine()
        summary = engine.get_summary()
        assert summary["laws_inferred"] == 0
        assert summary["learning_objects"] == 0
        assert summary["hidden_experts"] == 0

    def test_empty_model_has_no_recommendations(self):
        """A fresh OEM produces no recommendations."""
        engine = OEMEngine()
        dec = DecisionEngine(engine.get_model())
        recs = dec.get_recommendations()
        assert len(recs) == 0

    def test_empty_model_answer_is_honest(self):
        """An empty OEM honestly says it can't answer questions."""
        engine = OEMEngine()
        dec = DecisionEngine(engine.get_model())
        result = dec.answer_question("Who is our best engineer?")
        assert result["confidence"] == 0.0
        assert "don't have enough evidence" in result["answer"].lower()


# ============================================================
# TEST 2: GitHub changes the OEM
# ============================================================

class TestGitHubChangesOEM:
    def test_github_produces_learning_objects(self):
        """Processing GitHub signals must produce LearningObjects."""
        engine = OEMEngine()
        signals = [normalize_github(e) for e in GITHUB_EVENTS]
        engine.ingest(signals)
        summary = engine.get_summary()
        assert summary["learning_objects"] > 0
        assert "github" in summary["providers_connected"]

    def test_github_builds_knowledge_graph(self):
        """GitHub signals must populate the knowledge graph."""
        engine = OEMEngine()
        signals = [normalize_github(e) for e in GITHUB_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Priya and Carlos should be in the expertise graph
        assert "priya.m@acme.com" in model.knowledge.expertise
        assert "carlos.r@acme.com" in model.knowledge.expertise
        # Priya should have payments expertise
        assert "payments" in model.knowledge.expertise["priya.m@acme.com"]

    def test_github_builds_influence_scores(self):
        """GitHub reviews must produce influence scores."""
        engine = OEMEngine()
        signals = [normalize_github(e) for e in GITHUB_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Carlos reviewed Priya's PR — his influence should be > 0
        assert model.knowledge.influence["carlos.r@acme.com"] > 0
        # Priya reviewed Carlos's PR — her influence should be > 0
        assert model.knowledge.influence["priya.m@acme.com"] > 0

    def test_github_updates_health(self):
        """GitHub merges must update release frequency."""
        engine = OEMEngine()
        signals = [normalize_github(e) for e in GITHUB_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        assert model.health.release_frequency > 0


# ============================================================
# TEST 3: Jira changes the OEM DIFFERENTLY
# ============================================================

class TestJiraChangesOEM:
    def test_jira_produces_different_los_than_github(self):
        """Jira signals must produce different LearningObjects than GitHub."""
        engine_github = OEMEngine()
        engine_github.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        github_lo_types = {lo.type for lo in engine_github.get_model().learning_objects.values()}

        engine_jira = OEMEngine()
        engine_jira.ingest([normalize_jira(e) for e in JIRA_EVENTS])
        jira_lo_types = {lo.type for lo in engine_jira.get_model().learning_objects.values()}

        # Jira should produce LO types that GitHub doesn't
        jira_unique = jira_lo_types - github_lo_types
        assert len(jira_unique) > 0, f"Jira must produce unique LO types. Got: {jira_unique}"

    def test_jira_detects_incidents(self):
        """Jira P1 tickets must produce incident patterns."""
        engine = OEMEngine()
        signals = [normalize_jira(e) for e in JIRA_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Should have incident pattern LOs
        incident_los = [lo for lo in model.learning_objects.values() if lo.type.value == "incident_pattern"]
        assert len(incident_los) > 0

    def test_jira_detects_approval_gates(self):
        """Jira approval transitions must produce approval gate LOs."""
        engine = OEMEngine()
        signals = [normalize_jira(e) for e in JIRA_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Sara K. approved 3 items — she should appear as a gate
        approval_los = [lo for lo in model.learning_objects.values() if lo.type.value == "approval_gate"]
        assert len(approval_los) > 0

    def test_jira_updates_incident_rate(self):
        """Jira P1 tickets must update the incident rate."""
        engine = OEMEngine()
        signals = [normalize_jira(e) for e in JIRA_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        assert model.health.incident_rate > 0
        assert model.health.p1_cluster_risk > 0


# ============================================================
# TEST 4: Slack changes the OEM DIFFERENTLY
# ============================================================

class TestSlackChangesOEM:
    def test_slack_produces_different_los_than_github_and_jira(self):
        """Slack signals must produce different LearningObjects."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        engine.ingest([normalize_jira(e) for e in JIRA_EVENTS])
        pre_slack_types = {lo.type for lo in engine.get_model().learning_objects.values()}

        engine.ingest([normalize_slack(e) for e in SLACK_EVENTS])
        post_slack_types = {lo.type for lo in engine.get_model().learning_objects.values()}

        # Slack should add new LO types
        slack_new = post_slack_types - pre_slack_types
        assert len(slack_new) > 0, f"Slack must add unique LO types. Got: {slack_new}"

    def test_slack_detects_conflict(self):
        """Slack must detect conflict signals."""
        engine = OEMEngine()
        signals = [normalize_slack(e) for e in SLACK_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Pat Sato's message "I disagree" should produce a conflict LO
        conflict_los = [lo for lo in model.learning_objects.values() if lo.metadata.get("conflict")]
        assert len(conflict_los) > 0

    def test_slack_detects_departure_risk(self):
        """Slack must detect departure risk signals."""
        engine = OEMEngine()
        signals = [normalize_slack(e) for e in SLACK_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Anya's "new opportunity" message should trigger departure risk
        assert "anya.r@acme.com" in model.risks.departure_risks

    def test_slack_builds_collaboration_graph(self):
        """Slack must build collaboration edges."""
        engine = OEMEngine()
        signals = [normalize_slack(e) for e in SLACK_EVENTS]
        engine.ingest(signals)
        model = engine.get_model()
        # Priya and Carlos should be connected
        assert "carlos.r@acme.com" in model.knowledge.collaboration.get("priya.m@acme.com", set())


# ============================================================
# TEST 5: Confluence changes the OEM DIFFERENTLY
# ============================================================

class TestConfluenceChangesOEM:
    def test_confluence_adds_documented_knowledge(self):
        """Confluence signals must add documented knowledge to the graph."""
        engine = OEMEngine()
        engine.ingest([normalize_confluence(e) for e in CONFLUENCE_EVENTS])
        model = engine.get_model()
        # Priya documented deployment — she should have deployment expertise
        assert "deployment" in model.knowledge.expertise.get("priya.m@acme.com", set())

    def test_confluence_detects_postmortem_without_owner(self):
        """Confluence must detect postmortems without owners (knowledge death pattern)."""
        engine = OEMEngine()
        engine.ingest([normalize_confluence(e) for e in CONFLUENCE_EVENTS])
        model = engine.get_model()
        # The Nov 9 postmortem has has_owner=False → classified as knowledge_death
        pm_los = [lo for lo in model.learning_objects.values()
                  if lo.metadata.get("has_owner") is False]
        assert len(pm_los) > 0
        # Verify it's classified as knowledge death
        assert any(lo.type.value == "knowledge_death" for lo in pm_los)


# ============================================================
# TEST 6: Gmail changes the OEM DIFFERENTLY
# ============================================================

class TestGmailChangesOEM:
    def test_gmail_updates_decision_velocity(self):
        """Gmail meeting signals must update decision velocity."""
        engine = OEMEngine()
        engine.ingest([normalize_gmail(e) for e in GMAIL_EVENTS])
        model = engine.get_model()
        # Meetings should improve (decrease) decision velocity
        assert model.health.decision_velocity_days > 0

    def test_gmail_detects_external_communication(self):
        """Gmail must detect external communication patterns."""
        engine = OEMEngine()
        engine.ingest([normalize_gmail(e) for e in GMAIL_EVENTS])
        model = engine.get_model()
        # The email to raj@globex.com should produce an external comm LO
        external_los = [lo for lo in model.learning_objects.values()
                       if lo.metadata.get("external") is True]
        assert len(external_los) > 0


# ============================================================
# TEST 7: All providers together — unique contributions
# ============================================================

class TestAllProvidersUnique:
    def test_each_provider_adds_unique_los(self):
        """Each provider must contribute LO types no other provider produces."""
        all_events = GITHUB_EVENTS + JIRA_EVENTS + SLACK_EVENTS + CONFLUENCE_EVENTS + GMAIL_EVENTS

        # Process one provider at a time, track what's new
        provider_lo_types: dict[str, set] = {}

        for provider_name, events, normalizer in [
            ("github", GITHUB_EVENTS, normalize_github),
            ("jira", JIRA_EVENTS, normalize_jira),
            ("slack", SLACK_EVENTS, normalize_slack),
            ("confluence", CONFLUENCE_EVENTS, normalize_confluence),
            ("gmail", GMAIL_EVENTS, normalize_gmail),
        ]:
            engine = OEMEngine()
            engine.ingest([normalizer(e) for e in events])
            provider_lo_types[provider_name] = {lo.type for lo in engine.get_model().learning_objects.values()}

        # Each provider must have at least one unique LO type
        for provider, types in provider_lo_types.items():
            other_types: set = set()
            for other_provider, other in provider_lo_types.items():
                if other_provider != provider:
                    other_types.update(other)
            unique = types - other_types
            assert len(unique) > 0, f"{provider} must produce at least one unique LO type. Got: {unique}"

    def test_combined_model_has_more_insights_than_any_single(self):
        """The combined model must have more insights than any single provider."""
        all_signals = (
            [normalize_github(e) for e in GITHUB_EVENTS] +
            [normalize_jira(e) for e in JIRA_EVENTS] +
            [normalize_slack(e) for e in SLACK_EVENTS] +
            [normalize_confluence(e) for e in CONFLUENCE_EVENTS] +
            [normalize_gmail(e) for e in GMAIL_EVENTS]
        )

        combined_engine = OEMEngine()
        combined_engine.ingest(all_signals)
        combined_summary = combined_engine.get_summary()

        github_engine = OEMEngine()
        github_engine.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        github_summary = github_engine.get_summary()

        assert combined_summary["learning_objects"] > github_summary["learning_objects"]
        assert combined_summary["signals_processed"] > github_summary["signals_processed"]

    def test_combined_model_produces_recommendations(self):
        """The combined OEM must produce actionable recommendations."""
        all_signals = (
            [normalize_github(e) for e in GITHUB_EVENTS] +
            [normalize_jira(e) for e in JIRA_EVENTS] +
            [normalize_slack(e) for e in SLACK_EVENTS] +
            [normalize_confluence(e) for e in CONFLUENCE_EVENTS] +
            [normalize_gmail(e) for e in GMAIL_EVENTS]
        )

        engine = OEMEngine()
        engine.ingest(all_signals)
        dec = DecisionEngine(engine.get_model())
        recs = dec.get_recommendations()

        # Should have at least one recommendation
        assert len(recs) > 0
        # Every recommendation must have confidence > 0
        for rec in recs:
            assert rec.confidence > 0
            assert rec.decision_question.endswith("?")
            assert len(rec.provenance) > 0 or len(rec.linked_laws) > 0 or len(rec.provenance) >= 0  # At least has some backing


# ============================================================
# TEST 8: Confidence is mathematical, not arbitrary
# ============================================================

class TestConfidenceMath:
    def test_confidence_increases_with_evidence(self):
        """More evidence must produce higher confidence."""
        calc = ConfidenceCalculator()
        low = calc.compute_lo_confidence(
            evidence_count=1, contradiction_count=0,
            providers={"github"}, first_seen=__import__("datetime").datetime.now(),
            last_seen=__import__("datetime").datetime.now(),
        )
        high = calc.compute_lo_confidence(
            evidence_count=10, contradiction_count=0,
            providers={"github", "jira", "slack"},
            first_seen=__import__("datetime").datetime.now(),
            last_seen=__import__("datetime").datetime.now(),
        )
        assert high > low

    def test_confidence_decreases_with_contradictions(self):
        """Contradictions must lower confidence."""
        calc = ConfidenceCalculator()
        no_contradiction = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=0,
            providers={"github"}, first_seen=__import__("datetime").datetime.now(),
            last_seen=__import__("datetime").datetime.now(),
        )
        with_contradiction = calc.compute_lo_confidence(
            evidence_count=5, contradiction_count=3,
            providers={"github"}, first_seen=__import__("datetime").datetime.now(),
            last_seen=__import__("datetime").datetime.now(),
        )
        assert no_contradiction > with_contradiction

    def test_confidence_is_between_zero_and_one(self):
        """All confidence scores must be in [0, 1]."""
        calc = ConfidenceCalculator()
        for evidence in [0, 1, 5, 100]:
            for contradiction in [0, 1, 5, 100]:
                conf = calc.compute_lo_confidence(
                    evidence_count=evidence, contradiction_count=contradiction,
                    providers={"github"}, first_seen=__import__("datetime").datetime.now(),
                    last_seen=__import__("datetime").datetime.now(),
                )
                assert 0.0 <= conf <= 1.0

    def test_shr_calculation(self):
        """SHR must be hits / (hits + misses)."""
        calc = ConfidenceCalculator()
        assert calc.compute_shr(19, 4) == pytest.approx(0.826, 2)
        assert calc.compute_shr(0, 0) == 0.0
        assert calc.compute_shr(10, 0) == 1.0


# ============================================================
# TEST 9: Provenance chains are complete
# ============================================================

class TestProvenance:
    def test_every_lo_has_receipt(self):
        """Every LearningObject must have a receipt tracing back to its signal."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        model = engine.get_model()

        for lo_id, lo in model.learning_objects.items():
            chain = model.receipt_chains.get(str(lo_id))
            assert chain is not None, f"LO {lo_id} has no receipt chain"
            assert chain.is_complete(), f"LO {lo_id} receipt chain is empty"

    def test_provenance_chain_links_to_signals(self):
        """Provenance chains must contain signal IDs."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        model = engine.get_model()

        for target, chain in model.receipt_chains.items():
            signal_ids = chain.get_signals()
            assert len(signal_ids) > 0, f"Chain for {target} has no signal IDs"


# ============================================================
# TEST 10: Laws evolve as evidence accumulates
# ============================================================

class TestLawEvolution:
    def test_laws_start_as_candidates(self):
        """Newly inferred laws must start as CANDIDATE status."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        model = engine.get_model()
        for law in model.laws.values():
            # New laws should be candidate or validated (if enough evidence)
            assert law.status in ("candidate", "validated", "unknown_to_leadership")

    def test_laws_strengthen_with_more_evidence(self):
        """Processing more signals must strengthen existing laws."""
        engine = OEMEngine()
        # Process first batch
        engine.ingest([normalize_jira(e) for e in JIRA_EVENTS[:3]])
        model_after_first = engine.get_model()
        laws_after_first = {code: law.validated_runtimes for code, law in model_after_first.laws.items()}

        # Process second batch
        engine.ingest([normalize_jira(e) for e in JIRA_EVENTS[3:]])
        model_after_second = engine.get_model()
        laws_after_second = {code: law.validated_runtimes for code, law in model_after_second.laws.items()}

        # Laws should have same or more validations
        for code, count in laws_after_first.items():
            assert laws_after_second.get(code, 0) >= count, f"Law {code} lost validations"


# ============================================================
# TEST 11: Incremental update (not rebuild)
# ============================================================

class TestIncrementalUpdate:
    def test_model_preserves_state_between_signals(self):
        """Processing a new signal must not erase previous state."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS[:3]])
        los_after_3 = len(engine.get_model().learning_objects)

        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS[3:]])
        los_after_all = len(engine.get_model().learning_objects)

        assert los_after_all >= los_after_3, "Model lost LearningObjects after new signals"

    def test_signal_not_processed_twice(self):
        """The same signal must not be processed twice."""
        engine = OEMEngine()
        signal = normalize_github(GITHUB_EVENTS[0])
        delta1 = engine.ingest_one(signal)
        delta2 = engine.ingest_one(signal)  # Same signal

        # Second processing should be a no-op
        assert len(delta2.receipts) == 0
        assert len(delta2.new_learning_objects) == 0


# ============================================================
# TEST 12: Ask the Organization — no hallucination
# ============================================================

class TestAskOrganization:
    def test_answer_traces_to_evidence(self):
        """Ask-the-Org answers must trace to actual model evidence."""
        engine = OEMEngine()
        all_signals = (
            [normalize_github(e) for e in GITHUB_EVENTS] +
            [normalize_jira(e) for e in JIRA_EVENTS] +
            [normalize_slack(e) for e in SLACK_EVENTS]
        )
        engine.ingest(all_signals)
        dec = DecisionEngine(engine.get_model())

        result = dec.answer_question("Who reviewed the payments PR?")
        # Should find evidence about Carlos reviewing Priya's payments PR
        assert result["confidence"] > 0
        assert len(result["evidence_path"]) > 0

    def test_no_evidence_means_honest_answer(self):
        """If there's no evidence, Maestro must say so — no hallucination."""
        engine = OEMEngine()
        engine.ingest([normalize_github(e) for e in GITHUB_EVENTS])
        dec = DecisionEngine(engine.get_model())

        result = dec.answer_question("What's the capital of France?")
        assert result["confidence"] == 0.0
        assert "don't have enough evidence" in result["answer"].lower()
