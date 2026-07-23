"""Adapter package — T1 (open API) and T3 (business API + honest fallback) connectors.

T1 adapters (open, rich APIs):
  - slack.py: OAuth2 + conversations.history + Socket Mode
  - github.py: OAuth2/PAT + search API for PRs/issues/reviews
  - outlook.py: Graph delta sync + IMAP fallback

T3 adapters (walled business APIs + honest fallbacks):
  - fallback.py: forward-to-Maestro + honest labels for walled gardens

Each adapter registers itself via @register_adapter and implements BaseConnector.
All return Signal objects with the unified model.
"""
