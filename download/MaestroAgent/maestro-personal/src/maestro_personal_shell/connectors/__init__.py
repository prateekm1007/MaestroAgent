"""Maestro connector architecture — adapted from Onyx's Load/Poll/Slim pattern.

Each connector subclasses BaseConnector and implements:
  - load_from_state(): bulk initial sync
  - poll_source(start, end): incremental sync
  - slim_check(): return IDs of signals that still exist (for pruning)
  - load_credentials(): load OAuth tokens or API keys

SyncPoint stores the last sync state for incremental updates (PipesHub pattern).
"""
from maestro_personal_shell.connectors.base import BaseConnector, SyncPoint
from maestro_personal_shell.connectors.gmail import GmailConnector

__all__ = ["BaseConnector", "SyncPoint", "GmailConnector"]
