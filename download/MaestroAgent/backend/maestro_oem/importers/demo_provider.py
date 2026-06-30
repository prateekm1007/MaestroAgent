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

# Map provider name → its demo items. Each provider is one page.
_DEMO_PAGES: dict[str, list[dict[str, Any]]] = {
    "github": _GITHUB_ITEMS,
    "jira": _JIRA_ITEMS,
    "slack": _SLACK_ITEMS,
    "confluence": _CONFLUENCE_ITEMS,
    "gmail": _GMAIL_ITEMS,
}

# Map provider name → its normalizer (lazy import to avoid cycles).
_NORMALIZER_NAMES = {
    "github": "normalize_github",
    "jira": "normalize_jira",
    "slack": "normalize_slack",
    "confluence": "normalize_confluence",
    "gmail": "normalize_gmail",
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
