"""Shared base class for all provider fetchers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from maestro_oem.ingestion import PageFetcher, PageResult, PageStatus
from maestro_oem.oauth_manager import OAuthError, OAuthManager

logger = logging.getLogger(__name__)


class BaseProviderFetcher(PageFetcher):
    """Common HTTP/rate-limit/auth-refresh logic shared by all 5 fetchers."""

    provider: str = "base"
    base_url: str = ""
    page_size: int = 100

    def __init__(
        self,
        oauth: OAuthManager,
        http_client: httpx.AsyncClient | None = None,
        page_size: int | None = None,
        org_id: str | None = None,
    ) -> None:
        super().__init__(self.provider)
        self.oauth = oauth
        self.http = http_client or httpx.AsyncClient(timeout=30.0)
        if page_size:
            self.page_size = page_size
        self.org_id = org_id  # Jira cloud host, GitHub org, Slack team, etc.

    # ─── Auth header ───

    async def _auth_headers(self) -> dict[str, str]:
        """Return Authorization headers with a valid (refreshed) access token."""
        try:
            token = await self._get_token_async()
        except OAuthError:
            raise
        return self._build_auth_header(token)

    def _build_auth_header(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    async def _get_token_async(self) -> str:
        """Get a valid access token. Synchronous in OAuthManager, wrap for async."""
        # OAuthManager uses sync httpx internally; we run it in a thread
        # to avoid blocking the event loop on token refresh.
        import asyncio
        return await asyncio.to_thread(self.oauth.get_valid_access_token, self.provider)

    # ─── HTTP with retry ───

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an authenticated request, refreshing the token on 401."""
        headers = await self._auth_headers()
        if extra_headers:
            headers.update(extra_headers)

        resp = await self.http.request(
            method, url, params=params, json=json_body, headers=headers,
        )

        # If 401, try one refresh and retry
        if resp.status_code == 401:
            logger.info("Got 401 from %s, refreshing token", self.provider)
            try:
                token = await asyncio.to_thread(self.oauth.refresh_token, self.provider)
                headers = self._build_auth_header(token)
                if extra_headers:
                    headers.update(extra_headers)
                resp = await self.http.request(
                    method, url, params=params, json=json_body, headers=headers,
                )
            except OAuthError as e:
                logger.error("Token refresh failed for %s: %s", self.provider, e)
                raise

        return resp

    # ─── Rate-limit parsing ───

    @staticmethod
    def _parse_rate_limit_headers(
        resp: httpx.Response,
    ) -> tuple[int | None, datetime | None]:
        """Parse GitHub-style X-RateLimit-Remaining headers.

        Returns (remaining, reset_at). Both None if not present.
        """
        remaining = resp.headers.get("X-RateLimit-Remaining")
        reset = resp.headers.get("X-RateLimit-Reset")
        reset_at = None
        if reset:
            try:
                reset_at = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            except (ValueError, OSError):
                reset_at = None
        if remaining is not None:
            try:
                return int(remaining), reset_at
            except ValueError:
                pass
        return None, None

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> datetime | None:
        """Parse Retry-After header (Slack/Jira/Confluence/Gmail)."""
        retry = resp.headers.get("Retry-After")
        if not retry:
            return None
        try:
            # Could be seconds or HTTP date
            try:
                seconds = int(retry)
                from datetime import timedelta
                return datetime.now(timezone.utc) + timedelta(seconds=seconds)
            except ValueError:
                # HTTP date format
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(retry)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
        except Exception:
            return None

    # ─── PageResult builders ───

    def _rate_limited_result(self, resp: httpx.Response, page: int) -> PageResult:
        reset_at = self._parse_retry_after(resp)
        if reset_at is None:
            # GitHub style
            _, reset_at = self._parse_rate_limit_headers(resp)
        return PageResult(
            page_number=page,
            status=PageStatus.RATE_LIMITED,
            error=f"Rate limited by {self.provider}",
            rate_limit_remaining=0,
            rate_limit_reset_at=reset_at,
        )

    def _auth_expired_result(self, page: int) -> PageResult:
        return PageResult(
            page_number=page,
            status=PageStatus.AUTH_EXPIRED,
            error=f"Auth expired for {self.provider}",
        )

    def _error_result(self, page: int, msg: str) -> PageResult:
        return PageResult(
            page_number=page,
            status=PageStatus.ERROR,
            error=msg,
        )

    # ─── Subclasses must implement ───

    async def fetch_page(
        self,
        page: int = 1,
        cursor: str = "",
        since: datetime | None = None,
    ) -> PageResult:
        raise NotImplementedError

    async def estimate_total_pages(self, since: datetime | None = None) -> int:
        raise NotImplementedError

    async def refresh_auth(self) -> bool:
        try:
            await asyncio.to_thread(self.oauth.refresh_token, self.provider)
            return True
        except OAuthError:
            return False

    def normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Subclasses override to convert provider API item → event dict."""
        return item


# Late import to avoid circular
import asyncio  # noqa: E402
