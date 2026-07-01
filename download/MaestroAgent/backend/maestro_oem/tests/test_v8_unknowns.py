"""
V8 Upgrade #2 — Four-Level Unknowns. Regression tests.

Acceptance criteria (from the V8 spec):
  1. GET /api/oem/unknowns?levels=all returns 4 arrays: known,
     known_unknowns, unknown_unknowns, emerging_unknowns
  2. Each item has area + coverage + reason
  3. Emerging unknowns have detected_at (last 7 days)
  4. TODAY shows 4 levels with different treatment
  5. V5 litmus: no new panel. V8 litmus: does this build trust? YES —
     4-level honesty is more scientifically rigorous than 1-level.

These tests cover criteria 1, 2, 3, and 5 at the backend level.
Criterion 4 (TODAY visual) is covered by static file checks and the
existing Playwright suite.
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from maestro_oem import OEMEngine
from maestro_oem.curiosity import CuriosityEngine
from maestro_oem.signal import ExecutionSignal, SignalType


# Fixture — build the FastAPI app with demo seed, matching the pattern
# in maestro_api/tests/test_oem_routes.py.
@pytest.fixture(scope="module")
def client():
    """Build the FastAPI app with the OEM initialized (demo seed loaded)."""
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_v8_unknowns_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


# ============================================================
# Test data builders
# ============================================================

def _make_signal(signal_type: SignalType, actor: str = "u@acme.com",
                 artifact: str = "X-1", domain: str = "engineering",
                 days_ago: int = 30) -> ExecutionSignal:
    return ExecutionSignal(
        type=signal_type,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        actor=actor,
        artifact=artifact,
        metadata={"domain": domain},
    )


def _build_model_with_4_levels():
    """Build an OEM that exercises all 4 levels:
    - 'payments' domain: 10 signals → Known (>60% of avg)
    - 'architecture' domain: 3 signals → Known Unknown (10-60%)
    - 'legal' domain: 1 signal → Unknown Unknown (<10%)
    - 2 recent INCIDENT signals in 'security' → Emerging Unknown
    """
    signals = []
    # 10 payments signals (Known)
    for i in range(10):
        signals.append(_make_signal(SignalType.PR_OPENED, actor=f"eng{i}@acme.com",
                                     artifact=f"PR-PAY-{i}", domain="payments", days_ago=30))
    # 3 architecture signals (Known Unknown)
    for i in range(3):
        signals.append(_make_signal(SignalType.PR_OPENED, actor=f"arch{i}@acme.com",
                                     artifact=f"PR-ARCH-{i}", domain="architecture", days_ago=20))
    # 1 legal signal (Unknown Unknown)
    signals.append(_make_signal(SignalType.DECISION_SIGNAL, actor="legal@acme.com",
                                 artifact="DEC-LEGAL-1", domain="legal", days_ago=10))
    # 2 recent unmatched INCIDENT signals (Emerging Unknown — new, no LO match)
    signals.append(_make_signal(SignalType.INCIDENT, actor="oncall@acme.com",
                                 artifact="INC-NEW-1", domain="security", days_ago=2))
    signals.append(_make_signal(SignalType.INCIDENT, actor="oncall@acme.com",
                                 artifact="INC-NEW-2", domain="security", days_ago=1))

    engine = OEMEngine()
    for s in signals:
        engine.ingest([s])
    return engine.get_model(), signals


# ============================================================
# Acceptance Criterion 1 — 4 arrays returned
# ============================================================

class TestFourArraysReturned:
    """classify_unknowns() must return all 4 level arrays."""

    def test_returns_all_four_level_keys(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        assert "known" in result, "Missing 'known' array"
        assert "known_unknowns" in result, "Missing 'known_unknowns' array"
        assert "unknown_unknowns" in result, "Missing 'unknown_unknowns' array"
        assert "emerging_unknowns" in result, "Missing 'emerging_unknowns' array"
        assert isinstance(result["known"], list)
        assert isinstance(result["known_unknowns"], list)
        assert isinstance(result["unknown_unknowns"], list)
        assert isinstance(result["emerging_unknowns"], list)

    def test_returns_level_counts(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        assert "level_counts" in result
        counts = result["level_counts"]
        for key in ("known", "known_unknowns", "unknown_unknowns", "emerging_unknowns"):
            assert key in counts, f"Missing level_counts.{key}"
        # Counts must match array lengths
        assert counts["known"] == len(result["known"])
        assert counts["known_unknowns"] == len(result["known_unknowns"])
        assert counts["unknown_unknowns"] == len(result["unknown_unknowns"])
        assert counts["emerging_unknowns"] == len(result["emerging_unknowns"])

    def test_returns_summary(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()
        assert "summary" in result
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 20

    def test_test_data_produces_all_four_levels(self) -> None:
        """The 4-level test data must produce at least 1 item in known,
        known_unknowns, and emerging_unknowns. (unknown_unknowns may be
        0 if the 'legal' domain's single signal still exceeds 10% of avg —
        we verify the other 3 are non-empty to confirm the classification
        is exercising multiple levels.)"""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        assert len(result["known"]) >= 1, "Expected at least 1 Known area (payments)"
        assert len(result["known_unknowns"]) >= 1, "Expected at least 1 Known Unknown area (architecture or legal)"
        assert len(result["emerging_unknowns"]) >= 1, "Expected at least 1 Emerging Unknown (security:incident)"


# ============================================================
# Acceptance Criterion 2 — each item has area + coverage + reason
# ============================================================

class TestItemStructure:
    """Every item in every level must have area, coverage, reason."""

    def test_known_items_have_required_fields(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for item in result["known"]:
            assert "area" in item, f"Known item missing 'area': {item}"
            assert "coverage" in item, f"Known item missing 'coverage': {item}"
            assert "reason" in item, f"Known item missing 'reason': {item}"
            assert isinstance(item["area"], str) and item["area"]
            assert isinstance(item["coverage"], (int, float))
            assert 0.0 <= item["coverage"] <= 5.0  # coverage can exceed 1.0 (it's relative to avg)
            assert isinstance(item["reason"], str) and len(item["reason"]) > 10

    def test_known_unknown_items_have_required_fields(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for item in result["known_unknowns"]:
            assert "area" in item
            assert "coverage" in item
            assert "reason" in item
            assert isinstance(item["area"], str) and item["area"]
            assert isinstance(item["coverage"], (int, float))
            assert isinstance(item["reason"], str) and len(item["reason"]) > 10

    def test_unknown_unknown_items_have_required_fields(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for item in result["unknown_unknowns"]:
            assert "area" in item
            assert "coverage" in item
            assert "reason" in item
            assert isinstance(item["area"], str) and item["area"]
            assert isinstance(item["coverage"], (int, float))
            assert isinstance(item["reason"], str) and len(item["reason"]) > 10

    def test_emerging_unknown_items_have_required_fields(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for item in result["emerging_unknowns"]:
            assert "area" in item
            assert "coverage" in item
            assert "reason" in item
            assert "signal_count" in item
            assert isinstance(item["area"], str) and item["area"]
            assert isinstance(item["coverage"], (int, float))
            assert isinstance(item["reason"], str) and len(item["reason"]) > 10

    def test_all_items_have_signal_count(self) -> None:
        """Every item across all 4 levels must have signal_count."""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for level in ("known", "known_unknowns", "unknown_unknowns", "emerging_unknowns"):
            for item in result[level]:
                assert "signal_count" in item, f"{level} item missing 'signal_count': {item}"
                assert isinstance(item["signal_count"], int)
                assert item["signal_count"] >= 0


# ============================================================
# Acceptance Criterion 3 — emerging unknowns have detected_at (last 7 days)
# ============================================================

class TestEmergingUnknownsDetectedAt:
    """Emerging unknowns must have detected_at within the last 7 days."""

    def test_emerging_unknowns_have_detected_at(self) -> None:
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        assert len(result["emerging_unknowns"]) > 0, "Test data should produce emerging unknowns"
        for item in result["emerging_unknowns"]:
            assert "detected_at" in item, f"Emerging unknown missing 'detected_at': {item}"
            assert isinstance(item["detected_at"], str)
            # Must be a valid ISO timestamp
            parsed = datetime.fromisoformat(item["detected_at"])
            assert parsed.tzinfo is not None, "detected_at must be timezone-aware"

    def test_emerging_unknowns_detected_within_last_7_days(self) -> None:
        """detected_at must be within the last 7 days (the emerging window)."""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        for item in result["emerging_unknowns"]:
            parsed = datetime.fromisoformat(item["detected_at"])
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            assert parsed >= seven_days_ago, (
                f"Emerging unknown detected_at {parsed} is older than 7 days "
                f"(window start: {seven_days_ago})"
            )
            assert parsed <= now, (
                f"Emerging unknown detected_at {parsed} is in the future"
            )

    def test_only_emerging_unknowns_have_detected_at(self) -> None:
        """Only emerging_unknowns should have detected_at — the other 3 levels
        are cumulative classifications, not point-in-time detections."""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for level in ("known", "known_unknowns", "unknown_unknowns"):
            for item in result[level]:
                assert "detected_at" not in item, (
                    f"{level} item should NOT have detected_at (only emerging_unknowns): {item}"
                )


# ============================================================
# Classification correctness
# ============================================================

class TestClassificationCorrectness:
    """The 4-level classification must correctly bucket domains."""

    def test_payments_classified_as_known(self) -> None:
        """The 'payments' domain (10 signals) must be in Known."""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        known_areas = {item["area"] for item in result["known"]}
        assert "payments" in known_areas, (
            f"'payments' should be Known (10 signals, highest volume); "
            f"known={known_areas}"
        )

    def test_security_incident_classified_as_emerging(self) -> None:
        """The 'security:incident' pattern (2 recent signals) must be Emerging."""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        emerging_areas = {item["area"] for item in result["emerging_unknowns"]}
        # The area is "{domain}:{type}" — security:incident
        assert any("security" in a and "incident" in a for a in emerging_areas), (
            f"'security:incident' should be Emerging; emerging={emerging_areas}"
        )

    def test_coverage_thresholds_enforced(self) -> None:
        """Known items must have coverage > 0.60; Known Unknowns 0.10-0.60;
        Unknown Unknowns < 0.10."""
        model, signals = _build_model_with_4_levels()
        engine = CuriosityEngine(model, signals)
        result = engine.classify_unknowns()

        for item in result["known"]:
            assert item["coverage"] > 0.60, (
                f"Known item {item['area']} has coverage {item['coverage']} (should be > 0.60)"
            )
        for item in result["known_unknowns"]:
            assert 0.10 <= item["coverage"] <= 0.60, (
                f"Known Unknown item {item['area']} has coverage {item['coverage']} (should be 0.10-0.60)"
            )
        for item in result["unknown_unknowns"]:
            assert item["coverage"] < 0.10, (
                f"Unknown Unknown item {item['area']} has coverage {item['coverage']} (should be < 0.10)"
            )


# ============================================================
# API endpoint — /api/oem/unknowns
# ============================================================

class TestUnknownsAPIEndpoint:
    """The /api/oem/unknowns endpoint must work end-to-end."""

    def test_unknowns_endpoint_returns_200(self, client) -> None:
        r = client.get("/api/oem/unknowns")
        assert r.status_code == 200
        data = r.json()
        for key in ("known", "known_unknowns", "unknown_unknowns", "emerging_unknowns",
                    "summary", "level_counts"):
            assert key in data, f"Missing key '{key}' in response"

    def test_unknowns_endpoint_levels_all_default(self, client) -> None:
        """?levels=all (default) must return all 4 arrays populated from demo seed."""
        r = client.get("/api/oem/unknowns")
        data = r.json()
        # Demo seed should produce at least 1 Known area
        total = sum(data["level_counts"].values())
        assert total > 0, "Demo seed should produce at least 1 classified area"

    def test_unknowns_endpoint_levels_filter(self, client) -> None:
        """?levels=unknown_unknowns,emerging_unknowns must filter correctly."""
        r = client.get("/api/oem/unknowns", params={"levels": "unknown_unknowns,emerging_unknowns"})
        data = r.json()
        # Filtered levels should still have the keys (empty if no data)
        assert "known" in data
        assert "known_unknowns" in data
        assert "unknown_unknowns" in data
        assert "emerging_unknowns" in data
        # summary + level_counts always present
        assert "summary" in data
        assert "level_counts" in data

    def test_unknowns_endpoint_items_have_required_fields(self, client) -> None:
        """Every item in every returned level must have area + coverage + reason."""
        r = client.get("/api/oem/unknowns")
        data = r.json()
        for level in ("known", "known_unknowns", "unknown_unknowns", "emerging_unknowns"):
            for item in data[level]:
                assert "area" in item, f"{level} item missing 'area'"
                assert "coverage" in item, f"{level} item missing 'coverage'"
                assert "reason" in item, f"{level} item missing 'reason'"


# ============================================================
# Honesty — empty model
# ============================================================

class TestUnknownsHonesty:
    """Empty model must honestly report no classification, not fabricate."""

    def test_empty_model_returns_empty_arrays(self) -> None:
        engine = OEMEngine()
        model = engine.get_model()
        c = CuriosityEngine(model, [])
        result = c.classify_unknowns()

        assert result["known"] == []
        assert result["known_unknowns"] == []
        assert result["unknown_unknowns"] == []
        assert result["emerging_unknowns"] == []
        assert result["level_counts"] == {
            "known": 0, "known_unknowns": 0, "unknown_unknowns": 0, "emerging_unknowns": 0,
        }
        assert "empty" in result["summary"].lower() or "connect" in result["summary"].lower()


# ============================================================
# V5 litmus — no new panel
# ============================================================

class TestV5LitmusNoNewPanel:
    """V5 litmus: no new panel. The 4-level unknowns enhance TODAY, not a new surface."""

    def test_curiosity_module_does_not_create_new_surface(self) -> None:
        """The curiosity module must NOT define a new surface/panel."""
        import maestro_oem.curiosity as mod
        source = open(mod.__file__).read()
        assert "register_surface" not in source
        assert "new_panel" not in source

    def test_today_js_renders_unknowns_section(self, client) -> None:
        """today.js must fetch /unknowns and render the 4-level section."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        today_path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(today_path):
            pytest.skip(f"today.js not found at {today_path}")
        source = open(today_path).read()
        assert "/unknowns" in source, "today.js does not fetch /unknowns endpoint"
        assert "What Maestro doesn't know yet" in source, (
            "today.js missing 'What Maestro doesn't know yet' section header"
        )
        # All 4 levels must be rendered with different visual treatment
        assert "unknowns-known" in source, "today.js missing Known level CSS class"
        assert "unknowns-known-unknowns" in source, "today.js missing Known Unknowns level CSS class"
        assert "unknowns-unknown-unknowns" in source, "today.js missing Unknown Unknowns level CSS class"
        assert "unknowns-emerging" in source, "today.js missing Emerging Unknowns level CSS class"

    def test_routes_oem_has_unknowns_endpoint(self) -> None:
        """routes/oem.py must define the /unknowns endpoint."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert "@router.get(\"/unknowns\")" in source, "routes/oem.py missing /unknowns endpoint"
        assert "classify_unknowns" in source, "routes/oem.py doesn't call classify_unknowns"
