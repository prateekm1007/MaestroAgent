"""OAuth credentials loader — reads oauth_credentials.json at startup.

This eliminates the need for environment variables. The user puts their
Google/Slack/GitHub OAuth credentials in oauth_credentials.json once,
and the backend automatically configures all connectors.

Usage (called at startup from api.py lifespan):
    from maestro_personal_shell.oauth_loader import load_oauth_credentials
    load_oauth_credentials()
"""
from __future__ import annotations

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def load_oauth_credentials() -> dict:
    """Load OAuth credentials from oauth_credentials.json and set env vars.

    This makes connectors work with zero env var setup — just put the
    credentials in the JSON file and restart the backend.

    Returns the loaded credentials dict (empty if file not found).
    """
    # Find the credentials file — check multiple locations
    search_paths = [
        Path.cwd() / "oauth_credentials.json",
        Path(__file__).resolve().parent.parent / "oauth_credentials.json",
        Path(__file__).resolve().parent / "oauth_credentials.json",
    ]

    creds = {}
    for path in search_paths:
        if path.exists():
            try:
                creds = json.loads(path.read_text())
                logger.info("OAuth credentials loaded from %s", path)
                break
            except Exception as e:
                logger.warning("Failed to read %s: %s", path, e)
                continue

    if not creds:
        logger.info("No oauth_credentials.json found — connectors will use demo mode")
        return {}

    # Map JSON keys to the env var names the connectors expect
    env_mapping = {
        "gmail": ("MAESTRO_GMAIL_CLIENT_ID", "MAESTRO_GMAIL_CLIENT_SECRET"),
        "calendar": ("MAESTRO_CALENDAR_CLIENT_ID", "MAESTRO_CALENDAR_CLIENT_SECRET"),
        "slack": ("MAESTRO_SLACK_CLIENT_ID", "MAESTRO_SLACK_CLIENT_SECRET"),
        "github": ("MAESTRO_GITHUB_CLIENT_ID", "MAESTRO_GITHUB_CLIENT_SECRET"),
    }

    loaded = []
    for provider, (id_key, secret_key) in env_mapping.items():
        provider_creds = creds.get(provider, {})
        client_id = provider_creds.get("client_id", "")
        client_secret = provider_creds.get("client_secret", "")

        if client_id and client_secret:
            # Only set if not already set in env (env vars take precedence)
            if not os.environ.get(id_key):
                os.environ[id_key] = client_id
            if not os.environ.get(secret_key):
                os.environ[secret_key] = client_secret
            loaded.append(provider)

    if loaded:
        logger.info("OAuth credentials activated for: %s", ", ".join(loaded))
    else:
        logger.info("No OAuth credentials found in oauth_credentials.json — demo mode")

    return creds
