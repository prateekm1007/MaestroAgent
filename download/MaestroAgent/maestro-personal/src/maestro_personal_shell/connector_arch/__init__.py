"""Connector architecture — Onyx Load/Poll/Slim pattern.

This package provides the BaseConnector abstract class and GmailConnector
implementation. It is separate from connectors.py (which provides
ConnectorStore for SQLite-backed OAuth token storage) to avoid module
shadowing.

Usage:
    from maestro_personal_shell.connector_arch import GmailConnector, BaseConnector
"""
from maestro_personal_shell.connector_arch.base import BaseConnector, SyncPoint
from maestro_personal_shell.connector_arch.gmail import GmailConnector

__all__ = ["BaseConnector", "SyncPoint", "GmailConnector"]
