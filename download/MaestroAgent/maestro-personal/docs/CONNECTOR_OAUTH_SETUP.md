# Connector OAuth Setup Guide

> **Created:** 2026-07-14 (V3 Change 17)
> **Purpose:** Step-by-step instructions for creating OAuth apps for each connector provider.

## Gmail + Calendar (Google)

1. Go to https://console.cloud.google.com/apis/credentials
2. Create OAuth 2.0 Client ID (Web application)
3. Add redirect URIs:
   - `http://localhost:8766/api/connectors/gmail/oauth/callback`
   - `http://localhost:8766/api/connectors/calendar/oauth/callback`
4. Enable Gmail API + Google Calendar API
5. Set environment variables:
   ```bash
   export MAESTRO_GMAIL_CLIENT_ID="your-client-id"
   export MAESTRO_GMAIL_CLIENT_SECRET="your-client-secret"
   export MAESTRO_GMAIL_REDIRECT_URI="http://localhost:8766/api/connectors/gmail/oauth/callback"
   export MAESTRO_CALENDAR_CLIENT_ID="your-client-id"
   export MAESTRO_CALENDAR_CLIENT_SECRET="your-client-secret"
   export MAESTRO_CALENDAR_REDIRECT_URI="http://localhost:8766/api/connectors/calendar/oauth/callback"
   ```

## Slack

1. Go to https://api.slack.com/apps
2. Create New App → From scratch
3. Name: "Maestro Personal"
4. OAuth & Permissions → Add scopes:
   - `channels:read`
   - `channels:history`
   - `im:history`
   - `chat:write`
5. OAuth & Permissions → Add Redirect URL:
   `http://localhost:8766/api/connectors/slack/oauth/callback`
6. Set environment variables:
   ```bash
   export MAESTRO_SLACK_CLIENT_ID="your-slack-app-client-id"
   export MAESTRO_SLACK_CLIENT_SECRET="your-slack-app-client-secret"
   export MAESTRO_SLACK_REDIRECT_URI="http://localhost:8766/api/connectors/slack/oauth/callback"
   ```

## GitHub

1. Go to https://github.com/settings/developers
2. New OAuth App
3. Application name: "Maestro Personal"
4. Authorization callback URL:
   `http://localhost:8766/api/connectors/github/oauth/callback`
5. Set environment variables:
   ```bash
   export MAESTRO_GITHUB_CLIENT_ID="your-github-oauth-app-client-id"
   export MAESTRO_GITHUB_CLIENT_SECRET="your-github-oauth-app-client-secret"
   export MAESTRO_GITHUB_REDIRECT_URI="http://localhost:8766/api/connectors/github/oauth/callback"
   ```

## After setting env vars

Restart the backend. The `is_gmail_configured()`, `is_slack_configured()`,
`is_github_configured()`, `is_calendar_configured()` functions will return
`True` and the connectors will use real OAuth instead of mock data.

Verify with:
```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8766/api/connectors
# Each provider should show oauth_configured: true
```
