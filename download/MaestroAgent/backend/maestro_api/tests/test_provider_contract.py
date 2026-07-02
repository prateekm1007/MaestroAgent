"""Test: canonical provider list matches the importer factory.

Principle 10: the prior "connector drift fix" added glean/guru/dust to
SUPPORTED_IMPORT_PROVIDERS but the importer factory has no implementations
for them. A user could connect via OAuth but the import would crash.

This test verifies the canonical list matches the factory's supported
providers. If a new provider is added to the canonical list without an
importer, this test fails.
"""

from __future__ import annotations

import pytest

from maestro_api.routes.imports import SUPPORTED_IMPORT_PROVIDERS
from maestro_oem.importers.factory import _FETCHER_CLASSES


def test_canonical_provider_list_matches_factory() -> None:
    """Every provider in SUPPORTED_IMPORT_PROVIDERS must have an importer.

    The canonical list is used to gate the OAuth connect flow. If a provider
    is listed but has no importer, OAuth connect succeeds but import crashes
    with ValueError — a CRITICAL contract drift.
    """
    factory_supported = set(_FETCHER_CLASSES.keys())
    canonical = set(SUPPORTED_IMPORT_PROVIDERS)

    # Every canonical provider must be supported by the factory.
    missing_importers = canonical - factory_supported
    assert not missing_importers, (
        f"Providers in SUPPORTED_IMPORT_PROVIDERS without importers: "
        f"{missing_importers}. These providers can be connected via OAuth "
        f"but will crash on import. Either add importers or remove from "
        f"the canonical list."
    )


def test_factory_providers_are_in_canonical_list() -> None:
    """Every factory provider should be in the canonical list.

    If a factory provider is missing from the canonical list, it's
    invisible to the OAuth connect flow — users can't connect to it
    even though the importer exists.
    """
    factory_supported = set(_FETCHER_CLASSES.keys())
    canonical = set(SUPPORTED_IMPORT_PROVIDERS)

    missing_from_canonical = factory_supported - canonical
    assert not missing_from_canonical, (
        f"Factory providers missing from SUPPORTED_IMPORT_PROVIDERS: "
        f"{missing_from_canonical}. These importers exist but users "
        f"can't connect to them."
    )
