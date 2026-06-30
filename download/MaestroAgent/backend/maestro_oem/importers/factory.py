"""
ProviderFactory — picks the right fetcher for a provider.

Single dispatch point so the HistoricalImportEngine doesn't need to know
about specific provider implementations.
"""

from __future__ import annotations

from typing import Any

from maestro_oem.importers.github_importer import GitHubPageFetcher
from maestro_oem.importers.jira_importer import JiraPageFetcher
from maestro_oem.importers.slack_importer import SlackPageFetcher
from maestro_oem.importers.confluence_importer import ConfluencePageFetcher
from maestro_oem.importers.gmail_importer import GmailPageFetcher
from maestro_oem.importers.salesforce_importer import SalesforcePageFetcher
from maestro_oem.ingestion import PageFetcher
from maestro_oem.oauth_manager import OAuthManager

import httpx


_FETCHER_CLASSES = {
    "github": GitHubPageFetcher,
    "jira": JiraPageFetcher,
    "slack": SlackPageFetcher,
    "confluence": ConfluencePageFetcher,
    "gmail": GmailPageFetcher,
    "customer": SalesforcePageFetcher,  # Customer Judgment Engine — Salesforce CRM
}


class ProviderFactory:
    """Factory for creating PageFetcher instances per provider."""

    def __init__(
        self,
        oauth: OAuthManager,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.oauth = oauth
        self.http = http_client

    def supported_providers(self) -> list[str]:
        return list(_FETCHER_CLASSES.keys())

    def create(
        self,
        provider: str,
        org_id: str | None = None,
        page_size: int | None = None,
    ) -> PageFetcher:
        """Create a fetcher for the given provider.

        Raises ValueError if provider is unknown.
        """
        if provider not in _FETCHER_CLASSES:
            raise ValueError(
                f"Unknown provider: {provider}. Supported: {self.supported_providers()}"
            )
        cls = _FETCHER_CLASSES[provider]
        return cls(
            oauth=self.oauth,
            http_client=self.http,
            page_size=page_size,
            org_id=org_id,
        )

    def is_supported(self, provider: str) -> bool:
        return provider in _FETCHER_CLASSES
