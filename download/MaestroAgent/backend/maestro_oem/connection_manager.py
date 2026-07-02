"""
ConnectionManager — tracks which providers are connected and orchestrates
the initial historical import on first connect.

Single source of truth for: "Is provider X connected? When? With what scope?"
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from maestro_oem.checkpoint_store import CheckpointStore
from maestro_oem.oauth_manager import OAuthManager

if TYPE_CHECKING:
    from maestro_oem.historical_engine import HistoricalImportEngine

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Tracks provider connections and triggers initial historical imports.

    Lifecycle:
      1. User clicks "Connect GitHub" in UI
      2. UI calls /api/oauth/github/start → OAuthManager.get_authorization_url
      3. User authorizes on GitHub
      4. GitHub redirects to /api/oauth/callback?provider=github&code=...&state=...
      5. OAuthManager.exchange_code stores the token
      6. ConnectionManager.on_connected("github") is called
      7. ConnectionManager kicks off a historical import in the background
    """

    def __init__(
        self,
        store: CheckpointStore,
        oauth: OAuthManager,
        import_engine: "HistoricalImportEngine | None" = None,
    ) -> None:
        self.store = store
        self.oauth = oauth
        self.import_engine = import_engine

    def set_import_engine(self, engine: "HistoricalImportEngine") -> None:
        self.import_engine = engine

    # ─── Status ───

    def is_connected(self, provider: str) -> bool:
        conn = self.store.get_connection(provider)
        return bool(conn and conn["connected"])

    def list_connections(self) -> list[dict[str, Any]]:
        return self.store.list_connections()

    def list_connected_providers(self) -> list[str]:
        return [c["provider"] for c in self.list_connections() if c["connected"]]

    def status(self) -> list[dict[str, Any]]:
        return self.oauth.status()

    # ─── Connect / disconnect ───

    def get_authorization_url(self, provider: str) -> tuple[str, str]:
        return self.oauth.get_authorization_url(provider)

    async def complete_connection(
        self, provider: str, code: str, state: str, org_id: str = "default"
    ) -> dict[str, Any]:
        """Complete the OAuth flow and trigger the initial historical import.

        Returns the credentials metadata (without the access_token).

        Round 57 C2 fix: this method was sync and called `async start_import`
        without await — the coroutine was never awaited, so imports never
        started. Now this method is async and properly awaits start_import.
        Round 65 C3 fix: org_id propagated to start_import so signals go to
        the correct org's OEM.
        """
        creds = self.oauth.exchange_code(provider, code, state)

        # Trigger historical import in the background
        if self.import_engine:
            try:
                job_id = await self.import_engine.start_import(
                    providers=[provider],
                    since="5y",  # 5 years of history per the spec
                    org_id=org_id,
                )
                logger.info(
                    "Started historical import job %s for newly-connected %s",
                    job_id, provider,
                )
                return {
                    "provider": provider,
                    "connected": True,
                    "import_job_id": job_id,
                }
            except Exception as e:
                logger.error("Failed to start import for %s: %s", provider, e)
                return {
                    "provider": provider,
                    "connected": True,
                    "import_error": str(e),
                }
        return {"provider": provider, "connected": True}

    def disconnect(self, provider: str) -> None:
        """Revoke tokens and mark provider as disconnected.

        Does NOT delete already-ingested signals (those are historical fact).
        """
        # Cancel any in-flight import for this provider
        if self.import_engine:
            self.import_engine.cancel_for_provider(provider)
        self.oauth.disconnect(provider)
        logger.info("Provider %s disconnected", provider)

    def refresh_connection(self, provider: str) -> bool:
        """Force a token refresh. Returns True on success."""
        try:
            self.oauth.refresh_token(provider)
            return True
        except Exception as e:
            logger.error("Refresh failed for %s: %s", provider, e)
            self.store.set_connection(provider, connected=False)
            return False
