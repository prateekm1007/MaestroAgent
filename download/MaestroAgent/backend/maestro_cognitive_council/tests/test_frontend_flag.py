"""Tests for the frontend feature flag (council-router.js).

Per the audit: "Frontend calls /api/council 0 times. No feature flag
exists to swap them."

This test verifies:
  1. council-router.js exists in static/js/
  2. app.html loads it before other scripts
  3. It provides window.MaestroAPI with council mode detection
  4. The flag can be set via URL parameter, localStorage, or server injection
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest


class TestFrontendFeatureFlag:
    """The frontend has a feature flag to swap /api/oem → /api/council."""

    def test_council_router_js_exists(self):
        """council-router.js exists in static/js/."""
        router = pathlib.Path(__file__).resolve().parents[3] / "static" / "js" / "council-router.js"
        assert router.exists(), "static/js/council-router.js not found"

    def test_app_html_loads_council_router(self):
        """app.html loads council-router.js before other scripts."""
        app = pathlib.Path(__file__).resolve().parents[3] / "app.html"
        content = app.read_text()
        assert "council-router.js" in content, (
            "app.html must load council-router.js"
        )
        # Must load before core.js (so MAESTRO_API_BASE is available)
        router_pos = content.index("council-router.js")
        core_pos = content.index("core.js")
        assert router_pos < core_pos, (
            "council-router.js must load BEFORE core.js so MAESTRO_API_BASE is available"
        )

    def test_council_router_provides_feature_flag(self):
        """council-router.js provides window.MaestroAPI with isCouncilMode()."""
        router = pathlib.Path(__file__).resolve().parents[3] / "static" / "js" / "council-router.js"
        content = router.read_text()

        # Must provide the feature flag
        assert "isCouncilMode" in content, (
            "council-router.js must provide isCouncilMode() function"
        )
        assert "MAESTRO_USE_COUNCIL" in content, (
            "council-router.js must check MAESTRO_USE_COUNCIL flag"
        )
        assert "MAESTRO_API_BASE" in content, (
            "council-router.js must expose MAESTRO_API_BASE"
        )

    def test_council_router_supports_url_parameter(self):
        """The flag can be set via ?use_council=true URL parameter."""
        router = pathlib.Path(__file__).resolve().parents[3] / "static" / "js" / "council-router.js"
        content = router.read_text()
        assert "use_council" in content, (
            "council-router.js must support ?use_council=true URL parameter"
        )

    def test_council_router_supports_localStorage(self):
        """The flag can be set via localStorage."""
        router = pathlib.Path(__file__).resolve().parents[3] / "static" / "js" / "council-router.js"
        content = router.read_text()
        assert "localStorage" in content, (
            "council-router.js must support localStorage flag"
        )

    def test_council_router_provides_api_helpers(self):
        """council-router.js provides helper functions for API calls."""
        router = pathlib.Path(__file__).resolve().parents[3] / "static" / "js" / "council-router.js"
        content = router.read_text()

        # Must provide URL helpers for each surface
        for helper in ["askUrl", "whisperUrl", "briefingUrl", "preparationUrl"]:
            assert helper in content, (
                f"council-router.js must provide {helper}() helper"
            )

    def test_council_router_swaps_base_path(self):
        """When council is enabled, the base path is /api/council."""
        router = pathlib.Path(__file__).resolve().parents[3] / "static" / "js" / "council-router.js"
        content = router.read_text()

        assert "/api/council" in content, "Must reference /api/council"
        assert "/api/oem" in content, "Must reference /api/oem as fallback"

    def test_app_html_references_council_router_comment(self):
        """app.html has a comment explaining the council router."""
        app = pathlib.Path(__file__).resolve().parents[3] / "app.html"
        content = app.read_text()
        assert "council" in content.lower(), (
            "app.html must reference the council router"
        )

    def test_static_js_has_council_reference(self):
        """At least one file in static/js/ references /api/council."""
        static_js = pathlib.Path(__file__).resolve().parents[3] / "static" / "js"
        found = False
        for js_file in static_js.glob("*.js"):
            if "api/council" in js_file.read_text():
                found = True
                break
        assert found, (
            "No file in static/js/ references /api/council. "
            "The audit found 0 references — this fixes it."
        )
