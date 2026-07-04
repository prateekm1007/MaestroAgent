"""DemoProvider — a PageFetcher that produces the acme-corp demo dataset.

This replaces the old hardcoded seed in oem_state.py. Instead of building
ExecutionSignals directly from GITHUB_EVENTS / JIRA_EVENTS / etc. constants
and bypassing the ingestion pipeline, the demo seed now goes through the
same path a real provider does:

    DemoProvider.fetch_page()  →  PageResult(items=[...])
    fetcher.normalize_item()   →  event dict
    normalize_github(event)    →  ExecutionSignal
    oem_engine.ingest([sig])   →  laws / patterns / recommendations

Why this matters:
  - The demo seed and real providers use the SAME code path. A bug in the
    ingestion pipeline would be caught in demo mode, not just in production.
  - The demo seed can be enabled/disabled with MAESTRO_DEMO_SEED=false,
    which previously was documented but not honored.
  - Future demo datasets (multiple customers, larger fixtures) can be added
    without touching oem_state.py — just add another page to this fetcher.

The demo data itself (the acme-corp events) is identical to the previous
hardcoded seed. Only the plumbing changed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from maestro_oem.ingestion import PageFetcher, PageResult, PageStatus


# ─── Demo dataset (acme-corp) ───────────────────────────────────────────────
# Same events as the previous hardcoded seed, kept here so the demo
# behavior is unchanged. Each list is one "page" of items per provider.

_GITHUB_ITEMS = [
    {"event_type": "pull_request", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/447", "timestamp": "2024-11-12T09:00:00Z",
     "metadata": {"action": "opened", "domain": "payments", "title": "Add circuit breaker"}},
    {"event_type": "review", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/447", "timestamp": "2024-11-12T09:30:00Z",
     "metadata": {"reviewer": "carlos.r@acme.com", "domain": "payments", "action": "approved"}},
    {"event_type": "merge", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/447", "timestamp": "2024-11-12T10:00:00Z",
     "metadata": {"domain": "payments", "action": "merged"}},
    {"event_type": "pull_request", "repository": "acme/auth-service", "actor": "carlos.r@acme.com",
     "artifact": "github:acme/auth-service/pull/102", "timestamp": "2024-11-10T14:00:00Z",
     "metadata": {"action": "opened", "domain": "auth", "title": "OAuth consolidation"}},
    {"event_type": "review", "repository": "acme/auth-service", "actor": "carlos.r@acme.com",
     "artifact": "github:acme/auth-service/pull/102", "timestamp": "2024-11-10T16:00:00Z",
     "metadata": {"reviewer": "priya.m@acme.com", "domain": "auth", "action": "approved"}},
    {"event_type": "commit", "repository": "acme/platform-tools", "actor": "aisha.k@acme.com",
     "artifact": "github:acme/platform-tools/commit/abc123", "timestamp": "2024-11-08T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "commit", "repository": "acme/platform-tools", "actor": "aisha.k@acme.com",
     "artifact": "github:acme/platform-tools/commit/def456", "timestamp": "2024-11-09T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "commit", "repository": "acme/platform-tools", "actor": "aisha.k@acme.com",
     "artifact": "github:acme/platform-tools/commit/ghi789", "timestamp": "2024-11-10T11:00:00Z",
     "metadata": {"domain": "platform"}},
    {"event_type": "pull_request", "repository": "acme/payments-edge", "actor": "priya.m@acme.com",
     "artifact": "github:acme/payments-edge/pull/448", "timestamp": "2024-11-13T09:00:00Z",
     "metadata": {"action": "opened", "domain": "payments", "title": "Retry logic"}},
    {"event_type": "pull_request", "repository": "acme/auth-service", "actor": "priya.m@acme.com",
     "artifact": "github:acme/auth-service/pull/103", "timestamp": "2024-11-14T09:00:00Z",
     "metadata": {"action": "opened", "domain": "auth", "title": "Token refresh"}},
    {"event_type": "pull_request", "repository": "acme/platform-tools", "actor": "priya.m@acme.com",
     "artifact": "github:acme/platform-tools/pull/50", "timestamp": "2024-11-15T09:00:00Z",
     "metadata": {"action": "opened", "domain": "platform", "title": "Build script"}},
]

_JIRA_ITEMS = [
    {"event_type": "issue_created", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1247", "timestamp": "2024-11-05T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_created", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1248", "timestamp": "2024-11-06T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_created", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1249", "timestamp": "2024-11-07T09:00:00Z",
     "metadata": {"priority": "P1", "issue_type": "Bug"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1247", "timestamp": "2024-11-08T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1248", "timestamp": "2024-11-09T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1249", "timestamp": "2024-11-10T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "sprint_completed", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:SPRINT-Q4-3", "timestamp": "2024-11-08T17:00:00Z",
     "metadata": {"velocity": 42}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1250", "timestamp": "2024-11-11T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_transitioned", "project": "EMEA", "actor": "sara.k@acme.com",
     "artifact": "jira:EMEA-1251", "timestamp": "2024-11-12T14:00:00Z",
     "metadata": {"transition": "Approved", "assignee": "sara.k@acme.com"}},
    {"event_type": "issue_assigned", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1252", "timestamp": "2024-11-12T15:00:00Z",
     "metadata": {"assignee": "sara.k@acme.com", "issue_type": "Story"}},
    {"event_type": "issue_assigned", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1253", "timestamp": "2024-11-13T15:00:00Z",
     "metadata": {"assignee": "sara.k@acme.com", "issue_type": "Story"}},
    {"event_type": "issue_assigned", "project": "EMEA", "actor": "chris.t@acme.com",
     "artifact": "jira:EMEA-1254", "timestamp": "2024-11-14T15:00:00Z",
     "metadata": {"assignee": "sara.k@acme.com", "issue_type": "Story"}},
]

_SLACK_ITEMS = [
    {"event_type": "message", "channel": "#engineering", "actor": "priya.m@acme.com",
     "artifact": "slack:C-123/p-1", "timestamp": "2024-11-12T09:14:00Z",
     "metadata": {"text": "the payments-edge circuit breaker is ready for review. who can take a look today?",
      "participants": ["priya.m@acme.com", "carlos.r@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "carlos.r@acme.com",
     "artifact": "slack:C-123/p-2", "timestamp": "2024-11-12T09:16:00Z",
     "metadata": {"text": "I can review after lunch. does this cover the retry logic too?",
      "participants": ["carlos.r@acme.com", "priya.m@acme.com"]}},
    {"event_type": "message", "channel": "#leadership", "actor": "pat.s@acme.com",
     "artifact": "slack:C-456/p-3", "timestamp": "2024-11-11T10:00:00Z",
     "metadata": {"text": "I disagree with the Q3 hiring plan — we need APAC not EMEA",
      "participants": ["pat.s@acme.com", "jane.d@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "marcus.t@acme.com",
     "artifact": "slack:C-123/p-4", "timestamp": "2024-11-12T09:22:00Z",
     "metadata": {"text": "security review needed? this touches auth flow",
      "participants": ["marcus.t@acme.com", "priya.m@acme.com"]}},
    {"event_type": "message", "channel": "#engineering", "actor": "anya.r@acme.com",
     "artifact": "slack:C-123/p-5", "timestamp": "2024-11-10T15:00:00Z",
     "metadata": {"text": "I'm thinking about a new opportunity...", "participants": ["anya.r@acme.com"]}},
    {"event_type": "message", "channel": "#leadership", "actor": "jane.d@acme.com",
     "artifact": "slack:C-456/p-6", "timestamp": "2024-11-11T10:05:00Z",
     "metadata": {"text": "let's go with the compromise — reduce EMEA by 3, add 2 APAC",
      "participants": ["jane.d@acme.com", "pat.s@acme.com"]}},
]

_CONFLUENCE_ITEMS = [
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "chris.t@acme.com",
     "artifact": "confluence:PM-2024-11-09", "timestamp": "2024-11-09T16:00:00Z",
     "metadata": {"title": "Postmortem: payments-edge incident Nov 9", "has_owner": False, "page_type": "postmortem"}},
    {"event_type": "rfc_created", "space": "Engineering", "actor": "carlos.r@acme.com",
     "artifact": "confluence:RFC-412", "timestamp": "2024-10-28T10:00:00Z",
     "metadata": {"title": "OAuth Consolidation RFC", "domain": "auth", "has_owner": True, "page_type": "rfc"}},
    {"event_type": "page_created", "space": "Engineering", "actor": "priya.m@acme.com",
     "artifact": "confluence:DOC-789", "timestamp": "2024-11-01T11:00:00Z",
     "metadata": {"title": "Deployment Runbook", "domain": "deployment", "page_type": "documentation"}},
    {"event_type": "page_created", "space": "Payments", "actor": "anya.r@acme.com",
     "artifact": "confluence:DOC-790", "timestamp": "2024-11-03T14:00:00Z",
     "metadata": {"title": "Payments Integration Guide", "domain": "payments", "page_type": "documentation"}},
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "chris.t@acme.com",
     "artifact": "confluence:PM-2024-10-15", "timestamp": "2024-10-15T16:00:00Z",
     "metadata": {"title": "Postmortem: auth-service incident Oct 15", "has_owner": False, "page_type": "postmortem"}},
    {"event_type": "postmortem_created", "space": "Engineering", "actor": "priya.m@acme.com",
     "artifact": "confluence:PM-2024-09-20", "timestamp": "2024-09-20T16:00:00Z",
     "metadata": {"title": "Postmortem: platform-tools incident Sep 20", "has_owner": True, "page_type": "postmortem"}},
]

_GMAIL_ITEMS = [
    {"event_type": "meeting_completed", "actor": "jane.d@acme.com",
     "artifact": "cal:event-001", "timestamp": "2024-11-11T15:00:00Z",
     "metadata": {"participants": ["jane.d@acme.com", "raj@globex.com"], "duration": 30, "subject": "Q4 renewal discussion"}},
    {"event_type": "email_sent", "actor": "jane.d@acme.com",
     "artifact": "gmail:msg-001", "timestamp": "2024-11-11T16:00:00Z",
     "metadata": {"recipient": "raj@globex.com", "recipient_type": "external", "subject": "Re: Q4 renewal discussion"}},
    {"event_type": "meeting_completed", "actor": "chris.t@acme.com",
     "artifact": "cal:event-002", "timestamp": "2024-11-08T10:00:00Z",
     "metadata": {"participants": ["chris.t@acme.com", "casey.f@acme.com", "priya.e@acme.com"], "duration": 45, "subject": "Eng leadership sync"}},
    {"event_type": "meeting_completed", "actor": "jane.d@acme.com",
     "artifact": "cal:event-003", "timestamp": "2024-11-12T09:00:00Z",
     "metadata": {"participants": ["jane.d@acme.com", "chris.t@acme.com", "casey.f@acme.com", "pat.s@acme.com"],
      "duration": 60, "subject": "Q3 Hiring Decision"}},
]

# ─── Customer demo dataset (3 enterprise customers) ─────────────────────────
# Models the organizational relationship between Acme (the seller) and three
# enterprise customers: Globex (healthy, expanding), Initech (drifting,
# at-risk), Hooli (churning). Each event is a relationship signal —
# meetings, emails, commitments, stage changes, objections, champion
# activity. No personal data; only business-role metadata.
#
# The dataset is designed to produce:
#   - Buying-committee patterns (3+ role signals per customer → law candidate)
#   - Commitment-health patterns (kept/broken ratios → law candidate)
#   - Drift patterns (champion_quiet signals → law candidate on Initech)
#   - Risk clusters (objections on Hooli → law candidate)

_CUSTOMER_ITEMS = [
    # ─── Globex: healthy, expanding relationship ───────────────────────────
    # Champion: raj@globex.com (active). Economic buyer: sam@globex.com.
    # ARR at stake: $3.2M. Story: renewal progressing, SSO commitment made+kept.
    {"event_type": "meeting", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-mtg-1", "timestamp": "2024-10-15T10:00:00Z",
     "metadata": {"customer": "Globex", "contact": "raj@globex.com", "role": "champion",
                  "arr_impact": 3200000, "subject": "Q4 renewal kickoff",
                  "participants": ["jane.d@acme.com", "raj@globex.com"]}},
    {"event_type": "meeting", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-mtg-2", "timestamp": "2024-10-22T14:00:00Z",
     "metadata": {"customer": "Globex", "contact": "sam@globex.com", "role": "economic_buyer",
                  "arr_impact": 3200000, "subject": "Pricing review",
                  "participants": ["jane.d@acme.com", "sam@globex.com"]}},
    {"event_type": "meeting", "actor": "chris.t@acme.com",
     "artifact": "crm:globex-mtg-3", "timestamp": "2024-10-29T11:00:00Z",
     "metadata": {"customer": "Globex", "contact": "alex@globex.com", "role": "technical_buyer",
                  "arr_impact": 3200000, "subject": "Architecture review",
                  "participants": ["chris.t@acme.com", "alex@globex.com"]}},
    {"event_type": "commitment_made", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-commit-1", "timestamp": "2024-11-01T09:00:00Z",
     "metadata": {"customer": "Globex", "contact": "raj@globex.com", "role": "champion",
                  "arr_impact": 3200000, "commitment": "Deliver SSO by 2024-12-15",
                  "due_date": "2024-12-15"}},
    # Phase 2.2 demo seed: a MUTATED Globex commitment with a near-term due date.
    # This gives the CommitmentMutationTracker real history to project from
    # (commitment wording + deadline changed), so the Trajectory panel on
    # the Today surface shows scope_expansion pattern + medium risk +
    # Day-1/7/30/60 trajectory out of the box — without manual API seeding.
    # The due date (2026-07-15) is within the briefing's 30-day forward
    # window, so the commitment appears in the ceo-briefing's "due soon"
    # list and the Trajectory button is reachable on the unmodified Today
    # surface.
    {"event_type": "commitment_made", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-commit-2", "timestamp": "2025-06-01T14:00:00Z",
     "metadata": {"customer": "Globex", "contact": "raj@globex.com", "role": "champion",
                  "arr_impact": 3200000, "commitment": "Deliver SSO + MFA by 2026-07-15",
                  "due_date": "2026-07-15"}},
    {"event_type": "commitment_kept", "actor": "chris.t@acme.com",
     "artifact": "crm:globex-commit-1-kept", "timestamp": "2024-12-10T16:00:00Z",
     "metadata": {"customer": "Globex", "contact": "raj@globex.com", "role": "champion",
                  "arr_impact": 3200000, "commitment": "Deliver SSO by 2024-12-15"}},
    {"event_type": "champion_active", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-champ-1", "timestamp": "2024-12-12T10:00:00Z",
     "metadata": {"customer": "Globex", "contact": "raj@globex.com", "role": "champion",
                  "arr_impact": 3200000}},
    {"event_type": "stage_change", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-stage-1", "timestamp": "2024-12-15T12:00:00Z",
     "metadata": {"customer": "Globex", "contact": "raj@globex.com", "role": "champion",
                  "arr_impact": 3200000, "stage": "negotiation"}},
    {"event_type": "decision", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-dec-1", "timestamp": "2024-12-20T15:00:00Z",
     "metadata": {"customer": "Globex", "contact": "sam@globex.com", "role": "economic_buyer",
                  "arr_impact": 3200000, "decision_outcome": "renewed"}},
    {"event_type": "contract_renewed", "actor": "jane.d@acme.com",
     "artifact": "crm:globex-contract-1", "timestamp": "2025-01-05T10:00:00Z",
     "metadata": {"customer": "Globex", "contact": "sam@globex.com", "role": "economic_buyer",
                  "arr_impact": 3200000, "contract_value": 3200000}},

    # ─── Initech: drifting, at-risk relationship ───────────────────────────
    # Champion: priya@initech.com (went quiet). Economic buyer: max@initech.com.
    # ARR at stake: $1.8M. Story: champion disengaged, broken commitment,
    # objection on pricing. Should produce drift + risk patterns.
    {"event_type": "meeting", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-mtg-1", "timestamp": "2024-09-10T10:00:00Z",
     "metadata": {"customer": "Initech", "contact": "priya@initech.com", "role": "champion",
                  "arr_impact": 1800000, "subject": "Renewal discussion",
                  "participants": ["jane.d@acme.com", "priya@initech.com"]}},
    {"event_type": "meeting", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-mtg-2", "timestamp": "2024-09-20T14:00:00Z",
     "metadata": {"customer": "Initech", "contact": "max@initech.com", "role": "economic_buyer",
                  "arr_impact": 1800000, "subject": "Pricing negotiation",
                  "participants": ["jane.d@acme.com", "max@initech.com"]}},
    {"event_type": "meeting", "actor": "chris.t@acme.com",
     "artifact": "crm:initech-mtg-3", "timestamp": "2024-10-05T11:00:00Z",
     "metadata": {"customer": "Initech", "contact": "ben@initech.com", "role": "security",
                  "arr_impact": 1800000, "subject": "Security review",
                  "participants": ["chris.t@acme.com", "ben@initech.com"]}},
    {"event_type": "commitment_made", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-commit-1", "timestamp": "2024-10-10T09:00:00Z",
     "metadata": {"customer": "Initech", "contact": "priya@initech.com", "role": "champion",
                  "arr_impact": 1800000, "commitment": "Deliver SOC2 report by 2024-11-15",
                  "due_date": "2024-11-15"}},
    {"event_type": "commitment_broken", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-commit-1-broken", "timestamp": "2024-11-20T16:00:00Z",
     "metadata": {"customer": "Initech", "contact": "priya@initech.com", "role": "champion",
                  "arr_impact": 1800000, "commitment": "Deliver SOC2 report by 2024-11-15"}},
    {"event_type": "objection", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-obj-1", "timestamp": "2024-11-25T10:00:00Z",
     "metadata": {"customer": "Initech", "contact": "max@initech.com", "role": "economic_buyer",
                  "arr_impact": 1800000, "objection_type": "pricing"}},
    {"event_type": "champion_quiet", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-quiet-1", "timestamp": "2024-12-01T00:00:00Z",
     "metadata": {"customer": "Initech", "contact": "priya@initech.com", "role": "champion",
                  "arr_impact": 1800000}},
    {"event_type": "champion_quiet", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-quiet-2", "timestamp": "2024-12-15T00:00:00Z",
     "metadata": {"customer": "Initech", "contact": "priya@initech.com", "role": "champion",
                  "arr_impact": 1800000}},
    {"event_type": "objection", "actor": "jane.d@acme.com",
     "artifact": "crm:initech-obj-2", "timestamp": "2025-01-05T10:00:00Z",
     "metadata": {"customer": "Initech", "contact": "max@initech.com", "role": "economic_buyer",
                  "arr_impact": 1800000, "objection_type": "timeline"}},

    # ─── Hooli: churning relationship ──────────────────────────────────────
    # Champion: carl@hooli.com (left). ARR at stake: $2.4M (lost).
    # Story: champion departed, multiple objections, contract churned.
    {"event_type": "meeting", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-mtg-1", "timestamp": "2024-08-05T10:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "carl@hooli.com", "role": "champion",
                  "arr_impact": 2400000, "subject": "Renewal kickoff",
                  "participants": ["jane.d@acme.com", "carl@hooli.com"]}},
    {"event_type": "meeting", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-mtg-2", "timestamp": "2024-08-20T14:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "vincent@hooli.com", "role": "economic_buyer",
                  "arr_impact": 2400000, "subject": "Pricing discussion",
                  "participants": ["jane.d@acme.com", "vincent@hooli.com"]}},
    {"event_type": "objection", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-obj-1", "timestamp": "2024-09-01T10:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "vincent@hooli.com", "role": "economic_buyer",
                  "arr_impact": 2400000, "objection_type": "pricing"}},
    {"event_type": "objection", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-obj-2", "timestamp": "2024-09-15T10:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "vincent@hooli.com", "role": "economic_buyer",
                  "arr_impact": 2400000, "objection_type": "features"}},
    {"event_type": "champion_quiet", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-quiet-1", "timestamp": "2024-10-01T00:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "carl@hooli.com", "role": "champion",
                  "arr_impact": 2400000}},
    {"event_type": "commitment_broken", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-commit-1-broken", "timestamp": "2024-10-15T16:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "vincent@hooli.com", "role": "economic_buyer",
                  "arr_impact": 2400000, "commitment": "Custom integration by Q3"}},
    {"event_type": "decision", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-dec-1", "timestamp": "2024-11-01T15:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "vincent@hooli.com", "role": "economic_buyer",
                  "arr_impact": 2400000, "decision_outcome": "churned"}},
    {"event_type": "contract_churned", "actor": "jane.d@acme.com",
     "artifact": "crm:hooli-churn-1", "timestamp": "2024-11-10T10:00:00Z",
     "metadata": {"customer": "Hooli", "contact": "vincent@hooli.com", "role": "economic_buyer",
                  "arr_impact": 2400000, "contract_value": 2400000}},
]

# Map provider name → its demo items. Each provider is one page.
_DEMO_PAGES: dict[str, list[dict[str, Any]]] = {
    "github": _GITHUB_ITEMS,
    "jira": _JIRA_ITEMS,
    "slack": _SLACK_ITEMS,
    "confluence": _CONFLUENCE_ITEMS,
    "gmail": _GMAIL_ITEMS,
    "customer": _CUSTOMER_ITEMS,
}

# Map provider name → its normalizer (lazy import to avoid cycles).
_NORMALIZER_NAMES = {
    "github": "normalize_github",
    "jira": "normalize_jira",
    "slack": "normalize_slack",
    "confluence": "normalize_confluence",
    "gmail": "normalize_gmail",
    "customer": "normalize_customer",
}


def demo_provider_names() -> list[str]:
    """List of providers the DemoProvider can serve."""
    return list(_DEMO_PAGES.keys())


def demo_total_events() -> int:
    return sum(len(v) for v in _DEMO_PAGES.values())


class DemoPageFetcher(PageFetcher):
    """PageFetcher that yields a fixed demo dataset for one provider.

    Used at server startup to seed the OEM without requiring real OAuth
    credentials. The demo data goes through the SAME ingestion path as a
    real provider (fetch_page → normalize_item → provider normalizer →
    ExecutionSignal → OEMEngine.ingest), so a bug in the pipeline is
    caught in demo mode too.
    """

    def __init__(self, provider: str) -> None:
        super().__init__(provider)
        if provider not in _DEMO_PAGES:
            raise ValueError(
                f"DemoProvider does not support '{provider}'. "
                f"Supported: {list(_DEMO_PAGES.keys())}"
            )
        self._items = _DEMO_PAGES[provider]
        self._fetched = False  # One page per provider.

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        # Demo data is in-memory — no I/O. The async signature is kept so
        # this fetcher satisfies the PageFetcher interface used by the real
        # ingestion pipeline. For synchronous callers (e.g. OEMState
        # seeding at startup, which may already be inside a running event
        # loop in FastAPI TestClient), use fetch_page_sync().
        return self.fetch_page_sync(page, cursor, since)

    def fetch_page_sync(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        """Synchronous version of fetch_page for in-memory demo data.

        Used at startup when the caller may already be inside a running
        event loop (FastAPI TestClient). The real provider fetchers do
        NOT have a sync version — they do real I/O and must be awaited.
        """
        if page > 1 or self._fetched:
            return PageResult(
                page_number=page,
                status=PageStatus.SUCCESS,
                items=[],
                items_count=0,
                next_page=None,
                next_cursor=None,
                rate_limit_remaining=9999,
            )
        self._fetched = True
        items = list(self._items)
        return PageResult(
            page_number=1,
            status=PageStatus.SUCCESS,
            items=items,
            items_count=len(items),
            next_page=None,
            next_cursor=None,
            rate_limit_remaining=9999,
        )

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        return 1

    async def refresh_auth(self) -> bool:
        return True  # No auth needed for demo data.

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        # Demo items are already normalized event dicts.
        return item


def get_demo_normalizer(provider: str):
    """Return the provider-specific ExecutionSignal normalizer for the demo."""
    from maestro_oem import providers as _providers
    name = _NORMALIZER_NAMES.get(provider)
    if not name:
        raise ValueError(f"No demo normalizer for {provider}")
    return getattr(_providers, name)
