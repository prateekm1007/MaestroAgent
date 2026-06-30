"""Unit tests for Jira, Slack, Confluence, Gmail importers — uses httpx MockTransport."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.oauth_manager import OAuthManager
from maestro_oem.importers.jira_importer import JiraPageFetcher, ATLASSIAN_API
from maestro_oem.importers.slack_importer import SlackPageFetcher, SLACK_API
from maestro_oem.importers.confluence_importer import ConfluencePageFetcher
from maestro_oem.importers.gmail_importer import GmailPageFetcher, GMAIL_API


@pytest.fixture
def store(tmp_path):
    s = CheckpointStore(str(tmp_path / "test.db"))
    yield s
    s.close()


@pytest.fixture
def oauth(store):
    for p in ("jira", "slack", "confluence", "gmail"):
        store.save_credentials(provider=p, access_token=f"token_{p}", scopes=["test"])
        store.set_connection(p, connected=True)
    return OAuthManager(store)


# ─── Jira ───

@pytest.mark.asyncio
async def test_jira_fetcher_normalizes_issue(oauth, store):
    """Jira issue should produce created + transition events."""

    def handler(request: httpx.Request) -> httpx.Response:
        if "/me" in request.url.path:
            return httpx.Response(200, json={
                "accessibleResources": [{"id": "cloud-123", "name": "acme"}]
            })
        if "/search" in request.url.path:
            return httpx.Response(200, json={
                "total": 1,
                "issues": [{
                    "key": "PROJ-1",
                    "fields": {
                        "summary": "Bug fix",
                        "status": {"name": "Done"},
                        "reporter": {"emailAddress": "alice@acme.com", "accountId": "u1"},
                        "priority": {"name": "P1"},
                        "issuetype": {"name": "Bug"},
                        "created": "2024-06-01T00:00:00.000+0000",
                        "updated": "2024-06-02T00:00:00.000+0000",
                        "comment": {"comments": []},
                    },
                    "changelog": {
                        "histories": [{
                            "created": "2024-06-01T12:00:00.000+0000",
                            "author": {"emailAddress": "bob@acme.com", "accountId": "u2"},
                            "items": [{"field": "status", "fromString": "Open", "toString": "Done"}],
                        }]
                    },
                }],
            })
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = JiraPageFetcher(oauth, http_client=http_client)
    result = await fetcher.fetch_page(page=1, cursor="", since=None)

    assert result.status.value == "success"
    # Should produce at least 2 events: created + transition
    assert result.items_count >= 2
    types = [i["event_type"] for i in result.items]
    assert "issue_created" in types
    assert "issue_transitioned" in types
    await http_client.aclose()


@pytest.mark.asyncio
async def test_jira_rate_limit_handling(oauth, store):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/me" in request.url.path:
            return httpx.Response(200, json={"accessibleResources": [{"id": "c1"}]})
        return httpx.Response(429, headers={"Retry-After": "1"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = JiraPageFetcher(oauth, http_client=http_client)
    result = await fetcher.fetch_page(page=1, cursor="", since=None)
    assert result.status.value == "rate_limited"
    await http_client.aclose()


# ─── Slack ───

@pytest.mark.asyncio
async def test_slack_fetcher_normalizes_message(oauth, store):
    def handler(request: httpx.Request) -> httpx.Response:
        if "conversations.list" in request.url.path:
            return httpx.Response(200, json={
                "ok": True,
                "channels": [{"id": "C123", "name": "general"}],
                "response_metadata": {"next_cursor": ""},
            })
        if "conversations.history" in request.url.path:
            return httpx.Response(200, json={
                "ok": True,
                "messages": [{
                    "user": "U123", "text": "Hello team",
                    "ts": "1700000000.000100",
                    "thread_ts": None,
                    "reactions": [{"name": "thumbsup"}],
                }],
                "has_more": False,
                "response_metadata": {"next_cursor": ""},
            })
        if "users.list" in request.url.path:
            return httpx.Response(200, json={
                "ok": True,
                "members": [{
                    "id": "U123",
                    "profile": {"email": "alice@acme.com"},
                }],
                "response_metadata": {"next_cursor": ""},
            })
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = SlackPageFetcher(oauth, http_client=http_client)
    result = await fetcher.fetch_page(page=1, cursor="", since=None)

    assert result.status.value == "success"
    assert result.items_count == 1
    msg = result.items[0]
    assert msg["event_type"] == "message"
    assert "general" in msg["channel"]
    assert "alice@acme.com" in msg["actor"]
    assert msg["metadata"]["text"] == "Hello team"
    await http_client.aclose()


@pytest.mark.asyncio
async def test_slack_pagination_cursor(oauth, store):
    """Slack uses cursor-based pagination."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if "conversations.list" in request.url.path:
            return httpx.Response(200, json={
                "ok": True,
                "channels": [{"id": "C1", "name": "general"}],
                "response_metadata": {"next_cursor": ""},
            })
        if "conversations.history" in request.url.path:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(200, json={
                    "ok": True,
                    "messages": [{"user": "U1", "text": "msg1", "ts": "1700000000.000001"}],
                    "has_more": True,
                    "response_metadata": {"next_cursor": "next123"},
                })
            return httpx.Response(200, json={
                "ok": True,
                "messages": [],
                "has_more": False,
                "response_metadata": {"next_cursor": ""},
            })
        if "users.list" in request.url.path:
            return httpx.Response(200, json={
                "ok": True, "members": [],
                "response_metadata": {"next_cursor": ""},
            })
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = SlackPageFetcher(oauth, http_client=http_client)
    result1 = await fetcher.fetch_page(page=1, cursor="", since=None)
    assert result1.next_cursor  # Should advance to next cursor
    result2 = await fetcher.fetch_page(page=2, cursor=result1.next_cursor, since=None)
    assert result2.status.value == "success"
    await http_client.aclose()


# ─── Confluence ───

@pytest.mark.asyncio
async def test_confluence_fetcher_normalizes_page(oauth, store):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/me" in request.url.path:
            return httpx.Response(200, json={
                "accessibleResources": [{"id": "cloud-1"}]
            })
        if "/spaces" in request.url.path and "/pages" not in request.url.path:
            return httpx.Response(200, json={
                "results": [{"id": "1", "key": "ENG", "name": "Engineering"}],
                "_links": {"next": ""},
            })
        if "/pages" in request.url.path:
            return httpx.Response(200, json={
                "results": [{
                    "id": "p1", "title": "API Design Doc",
                    "authorId": "alice",
                    "createdAt": "2024-06-01T00:00:00Z",
                    "version": {"number": 2, "createdAt": "2024-06-02T00:00:00Z",
                                "authorId": "bob"},
                    "body": {"storage": {"value": "long content here"}},
                }],
                "_links": {"next": ""},
            })
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = ConfluencePageFetcher(oauth, http_client=http_client)
    result = await fetcher.fetch_page(page=1, cursor="", since=None)

    assert result.status.value == "success"
    # Should produce created + updated events (version 2 > 1)
    types = [i["event_type"] for i in result.items]
    assert "page_created" in types
    assert "page_updated" in types
    await http_client.aclose()


# ─── Gmail ───

@pytest.mark.asyncio
async def test_gmail_fetcher_normalizes_message(oauth, store):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/profile" in request.url.path:
            return httpx.Response(200, json={"emailAddress": "alice@acme.com"})
        if "/messages" in request.url.path and not request.url.path.endswith(tuple(str(i) for i in range(10))):
            return httpx.Response(200, json={
                "messages": [{"id": "msg1", "threadId": "t1"}],
                "nextPageToken": "",
            })
        if "/messages/msg1" in request.url.path:
            return httpx.Response(200, json={
                "id": "msg1", "threadId": "t1",
                "snippet": "Quick update on the project",
                "internalDate": "1700000000000",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Alice <alice@acme.com>"},
                        {"name": "To", "value": "bob@acme.com"},
                        {"name": "Subject", "value": "Project Update"},
                        {"name": "Date", "value": "Mon, 1 Jun 2024 00:00:00 +0000"},
                    ]
                }
            })
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = GmailPageFetcher(oauth, http_client=http_client)
    result = await fetcher.fetch_page(page=1, cursor="", since=None)

    assert result.status.value == "success"
    assert result.items_count == 1
    msg = result.items[0]
    assert msg["event_type"] == "email"
    assert "alice@acme.com" in msg["actor"]
    assert "alice@acme.com" in msg["metadata"]["participants"]
    assert "bob@acme.com" in msg["metadata"]["participants"]
    assert msg["metadata"]["subject"] == "Project Update"
    await http_client.aclose()


@pytest.mark.asyncio
async def test_gmail_rate_limit_handling(oauth, store):
    def handler(request: httpx.Request) -> httpx.Response:
        if "/profile" in request.url.path:
            return httpx.Response(200, json={"emailAddress": "me"})
        return httpx.Response(429, headers={"Retry-After": "1"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = GmailPageFetcher(oauth, http_client=http_client)
    result = await fetcher.fetch_page(page=1, cursor="", since=None)
    assert result.status.value == "rate_limited"
    await http_client.aclose()


# ─── Provider factory ───

def test_provider_factory_creates_all_providers(oauth):
    from maestro_oem.importers.factory import ProviderFactory
    factory = ProviderFactory(oauth)
    for p in ("github", "jira", "slack", "confluence", "gmail"):
        fetcher = factory.create(p)
        assert fetcher.provider == p


def test_provider_factory_unknown_provider(oauth):
    from maestro_oem.importers.factory import ProviderFactory
    factory = ProviderFactory(oauth)
    with pytest.raises(ValueError, match="Unknown provider"):
        factory.create("unknown")
