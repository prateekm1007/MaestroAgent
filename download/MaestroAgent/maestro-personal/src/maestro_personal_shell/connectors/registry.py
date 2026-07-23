"""Source adapter registry — maps source names to connector classes.

Every adapter registers itself here. The ingestion pipeline uses the
registry to find the right adapter for a given source.
"""
from __future__ import annotations

from typing import Type

from maestro_personal_shell.connectors.base import BaseConnector

_REGISTRY: dict[str, Type[BaseConnector]] = {}


def register_adapter(source: str):
    """Decorator: register a connector class for a source name.

    Usage:
        @register_adapter("slack")
        class SlackAdapter(BaseConnector):
            ...
    """
    def decorator(cls: Type[BaseConnector]) -> Type[BaseConnector]:
        cls.connector_name = source
        _REGISTRY[source] = cls
        return cls
    return decorator


def get_adapter(source: str) -> Type[BaseConnector] | None:
    """Look up the adapter class for a source name."""
    return _REGISTRY.get(source)


def list_adapters() -> dict[str, Type[BaseConnector]]:
    """Return all registered adapters."""
    return dict(_REGISTRY)


def available_sources() -> list[str]:
    """Return all registered source names."""
    return sorted(_REGISTRY.keys())
