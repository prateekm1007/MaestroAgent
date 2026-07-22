# connector_arch — NOT WIRED TO API (reference only)

This package provides the Onyx-pattern `BaseConnector` abstract class
and a `GmailConnector` implementation with Load/Poll/Slim methods.

**This code is NOT wired to any API endpoint.** It exists as an
architectural reference for the connector pattern.

The active Gmail implementation is in `gmail_connector.py` (the module,
not this package), which provides:
- `GmailOAuthClient` — OAuth flow (used by `/api/connectors/gmail/connect`)
- `GmailAPIClient` — Gmail API calls (list_messages, get_message, send_message)
- `GmailIngester` — email ingestion pipeline
- `is_gmail_configured()` — checks env vars

To migrate to the Onyx pattern in the future:
1. Wire `connector_arch/gmail.py` into the API endpoints
2. Move the OAuth logic from `gmail_connector.py` into `GmailConnector`
3. Deprecate `gmail_connector.py`

Until then, use `gmail_connector.py` for all production Gmail operations.
