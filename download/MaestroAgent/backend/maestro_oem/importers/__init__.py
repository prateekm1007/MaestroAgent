"""Real PageFetcher implementations for all 5 providers.

Each implementation:
  - Uses httpx to call the real provider API
  - Handles pagination per the provider's spec
  - Parses rate-limit headers (GitHub/Slack) or Retry-After (Jira/Confluence/Gmail)
  - Refreshes OAuth tokens via OAuthManager on 401
  - Normalizes raw API responses into the event dict shape expected
    by maestro_oem.providers.{provider}.normalize_{provider}

All fetchers are async (httpx.AsyncClient) so they can run concurrently
via HistoricalImportEngine.
"""

from maestro_oem.importers.github_importer import GitHubPageFetcher
from maestro_oem.importers.jira_importer import JiraPageFetcher
from maestro_oem.importers.slack_importer import SlackPageFetcher
from maestro_oem.importers.confluence_importer import ConfluencePageFetcher
from maestro_oem.importers.gmail_importer import GmailPageFetcher
from maestro_oem.importers.factory import ProviderFactory

__all__ = [
    "GitHubPageFetcher",
    "JiraPageFetcher",
    "SlackPageFetcher",
    "ConfluencePageFetcher",
    "GmailPageFetcher",
    "ProviderFactory",
]
