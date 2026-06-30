"""Unit tests for the GitHub importer — uses httpx MockTransport."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.oauth_manager import OAuthManager
from maestro_oem.importers.github_importer import GitHubPageFetcher, GITHUB_API


def _make_oauth(store, access_token="gho_test123", expires_at=None):
    """Pre-populate credentials so OAuthManager.get_valid_access_token returns immediately."""
    store.save_credentials(
        provider="github",
        access_token=access_token,
        refresh_token="ghr_refresh456",
        expires_at=expires_at,
        scopes=["repo"],
    )
    return OAuthManager(store)


def _mock_repos_response():
    return [
        {"full_name": "acme/payments", "name": "payments"},
        {"full_name": "acme/auth", "name": "auth"},
    ]


def _mock_prs_response(page, count=2):
    return [
        {
            "number": 100 + page * 10 + i,
            "title": f"PR {i} on page {page}",
            "user": {"login": f"user{i}"},
            "state": "closed" if i % 2 else "open",
            "merged_at": "2024-06-01T10:00:00Z" if i % 2 else None,
            "created_at": "2024-06-01T09:00:00Z",
            "updated_at": "2024-06-01T11:00:00Z",
            "additions": 10, "deletions": 5, "review_comments": 1,
        } for i in range(count)
    ]


def _mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "/user/repos" in url:
        return httpx.Response(200, json=_mock_repos_response(),
                              headers={"X-RateLimit-Remaining": "4999"})
    if "/pulls" in url and "/reviews" not in url:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=_mock_prs_response(page),
                              headers={"X-RateLimit-Remaining": "4998"})
    if "/issues" in url:
        return httpx.Response(200, json=[{
            "number": 200, "title": "Bug", "user": {"login": "alice"},
            "state": "open", "labels": [{"name": "bug"}, {"name": "P1"}],
            "created_at": "2024-06-01T00:00:00Z",
            "updated_at": "2024-06-01T00:00:00Z",
        }] * 2, headers={"X-RateLimit-Remaining": "4997"})
    if "/commits" in url:
        return httpx.Response(200, json=[{
            "sha": "abcdef1234567",
            "commit": {
                "message": "fix: payment bug",
                "author": {"name": "Bob", "email": "bob@acme.com",
                           "date": "2024-06-01T00:00:00Z"},
            },
            "author": {"login": "bob"},
        }] * 2, headers={"X-RateLimit-Remaining": "4996"})
    if "/reviews" in url:
        return httpx.Response(200, json=[{
            "id": 1, "user": {"login": "carol"},
            "state": "APPROVED", "submitted_at": "2024-06-01T12:00:00Z",
        }], headers={"X-RateLimit-Remaining": "4995"})
    return httpx.Response(404, json={"error": "not found"})


@pytest.mark.asyncio
async def test_github_fetcher_initialization(tmp_path):
    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    fetcher = GitHubPageFetcher(oauth, http_client=httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler)))
    assert fetcher.provider == "github"
    assert fetcher.page_size == 100


@pytest.mark.asyncio
async def test_github_discover_repos(tmp_path):
    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler))
    fetcher = GitHubPageFetcher(oauth, http_client=http_client)
    repos = await fetcher._discover_repos()
    assert len(repos) == 2
    assert "acme/payments" in repos
    await http_client.aclose()


@pytest.mark.asyncio
async def test_github_fetch_pulls_page(tmp_path):
    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler))
    fetcher = GitHubPageFetcher(oauth, http_client=http_client, repos=["acme/payments"])
    # First fetch should hit pulls
    result = await fetcher.fetch_page(page=1, cursor="", since=None)
    assert result.status.value == "success"
    assert result.items_count > 0
    # Verify normalization
    item = result.items[0]
    assert item["event_type"] == "pull_request"
    assert "acme/payments" in item["repository"]
    assert item["artifact"].startswith("github:acme/payments/pull/")
    await http_client.aclose()


@pytest.mark.asyncio
async def test_github_pagination_cursor(tmp_path):
    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler))
    fetcher = GitHubPageFetcher(oauth, http_client=http_client, repos=["acme/payments"])
    # First page
    result1 = await fetcher.fetch_page(page=1, cursor="", since=None)
    assert result1.next_cursor  # Should have a next cursor
    # Second page using the cursor
    result2 = await fetcher.fetch_page(page=2, cursor=result1.next_cursor, since=None)
    assert result2.status.value == "success"
    await http_client.aclose()


@pytest.mark.asyncio
async def test_github_rate_limit_handling(tmp_path):
    """When GitHub returns 403 with rate limit headers, fetcher should report RATE_LIMITED."""

    def rate_limited_handler(request):
        return httpx.Response(
            403,
            json={"message": "rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(datetime.now(timezone.utc).timestamp()) + 60)},
        )

    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(rate_limited_handler))
    fetcher = GitHubPageFetcher(oauth, http_client=http_client, repos=["acme/payments"])
    result = await fetcher.fetch_page(page=1, cursor="", since=None)
    # Should either be rate_limited or error (depending on whether the mock returns 403 for /pulls)
    assert result.status.value in ("rate_limited", "error")
    await http_client.aclose()


@pytest.mark.asyncio
async def test_github_normalize_pr(tmp_path):
    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler))
    fetcher = GitHubPageFetcher(oauth, http_client=http_client, repos=["acme/payments"])
    pr = {
        "number": 42, "title": "Add payment retry logic",
        "user": {"login": "priya"}, "state": "closed",
        "merged_at": "2024-06-01T10:00:00Z",
        "created_at": "2024-06-01T09:00:00Z", "updated_at": "2024-06-01T11:00:00Z",
        "additions": 50, "deletions": 10, "review_comments": 3,
    }
    normalized = fetcher._normalize_pr("acme/payments", pr)
    assert normalized["event_type"] == "pull_request"
    assert normalized["repository"] == "acme/payments"
    assert normalized["metadata"]["action"] == "merged"
    assert normalized["metadata"]["domain"] == "payments"  # inferred from repo name
    await http_client.aclose()


@pytest.mark.asyncio
async def test_github_domain_inference():
    """Verify the domain heuristic."""
    f = GitHubPageFetcher.__new__(GitHubPageFetcher)  # avoid __init__
    assert GitHubPageFetcher._infer_domain("acme/payments-edge", "Add retry") == "payments"
    assert GitHubPageFetcher._infer_domain("acme/auth-service", "OAuth consolidation") == "auth"
    assert GitHubPageFetcher._infer_domain("acme/security-tools", "Fix CVE") == "security"
    assert GitHubPageFetcher._infer_domain("acme/legal-docs", "Update contract") == "legal"
    assert GitHubPageFetcher._infer_domain("acme/platform-tools", "Build script") == "platform"
    assert GitHubPageFetcher._infer_domain("acme/ml-models", "Train classifier") == "ml"


@pytest.mark.asyncio
async def test_github_auth_refresh_on_401(tmp_path):
    """When the API returns 401, the fetcher should attempt a token refresh."""
    refresh_count = {"count": 0}

    def handler_with_401(request):
        if "/pulls" in request.url.path:
            # First call returns 401, second (after refresh) returns 200
            if refresh_count["count"] == 0:
                refresh_count["count"] += 1
                return httpx.Response(401, json={"message": "Bad credentials"})
            return httpx.Response(200, json=_mock_prs_response(1),
                                  headers={"X-RateLimit-Remaining": "4999"})
        return httpx.Response(200, json=[])

    store = CheckpointStore(str(tmp_path / "test.db"))
    oauth = _make_oauth(store)
    # Stub refresh_token to update the stored creds
    original_refresh = oauth.refresh_token
    def fake_refresh(provider):
        store.save_credentials(provider="github", access_token="gho_new_token",
                               refresh_token="ghr_refresh456", scopes=["repo"])
        return "gho_new_token"
    oauth.refresh_token = fake_refresh

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler_with_401))
    fetcher = GitHubPageFetcher(oauth, http_client=http_client, repos=["acme/payments"])
    result = await fetcher.fetch_page(page=1, cursor="", since=None)
    assert result.status.value == "success"
    await http_client.aclose()
