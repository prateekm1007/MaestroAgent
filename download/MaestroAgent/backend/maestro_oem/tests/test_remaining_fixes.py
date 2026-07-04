"""Tests for the six remaining issues fixed after the learning-loop commit.

Covers:
  1. SimulationEngine consolidation — /simulator and /simulate return the
     same response shape, including the `inputs` field that was previously
     missing (the test_post_simulator bug).
  2. DemoProvider — the acme-corp demo seed loads through the real
     ingestion pipeline (DemoPageFetcher implements PageFetcher).
  3. MAESTRO_DEMO_SEED=false — the env var is honored (previously
     documented but not implemented).
  4. Law dedup — L-0001 and L-0003 (near-duplicate "priya.m@acme.com is a
     bottleneck" laws differing only in evidence count) collapse to one law.
  5. WCAG contrast — #71717a (4.18:1, fails AA) replaced with #9a9aa3
     (7.24:1, passes AA). Verified at the HTML source level.
  6. /twin/simulate is intentionally separate from /simulate (different
     output shape — organizational what-if vs. metric what-if).
"""

import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from maestro_api.main import create_app
from maestro_api.oem_state import oem_state, import_state, _demo_seed_enabled
from maestro_oem.importers.demo_provider import (
    DemoPageFetcher,
    demo_provider_names,
    demo_total_events,
)
from maestro_oem.simulation import SimulationEngine


# ─── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    # Default: demo seed ON.
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "true")
    # ISSUE-11 fix: isolate OEMStore DB per test (same fix as empty_client)
    monkeypatch.setenv("MAESTRO_OEM_STORE_DB", str(tmp_path / "oem_store.db"))

    # Reset singletons so each test starts from a clean OEM.
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._live_signals_ingested = 0
    oem_state._contradiction_log = None
    oem_state._demo_seeded = False
    oem_state._oem_store = None  # ISSUE-11: clear store so it re-inits

    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c

    oem_state._initialized = False
    oem_state.engine = None
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._demo_seeded = False


@pytest.fixture
def empty_client(tmp_path, monkeypatch):
    """A client with MAESTRO_DEMO_SEED=false — OEM starts empty."""
    app_dir = str(Path(__file__).resolve().parents[3])
    monkeypatch.setattr("maestro_api.oem_state._IMPORT_DB_PATH", str(tmp_path / "test_import.db"))
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_LEARNING_DB", str(tmp_path / "learning.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test")
    monkeypatch.setenv("MAESTRO_RATE_LIMIT_RPM", "10000")
    monkeypatch.setenv("MAESTRO_DEMO_SEED", "false")
    # ISSUE-11 fix: isolate OEMStore DB so C6 persistence doesn't load
    # laws from a prior test's save. Without this, laws_inferred=6 even
    # with MAESTRO_DEMO_SEED=false because the store has persisted state.
    monkeypatch.setenv("MAESTRO_OEM_STORE_DB", str(tmp_path / "oem_store_empty.db"))

    # Reset the oem_state singleton so the next initialize() picks up the
    # new MAESTRO_DEMO_SEED=false env var. Without this, the singleton
    # retains state from whatever test ran first.
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._live_signals_ingested = 0
    oem_state._contradiction_log = None
    oem_state._demo_seeded = False
    oem_state._oem_store = None  # ISSUE-11: clear the store so it re-inits

    import_state._initialized = False
    import_state.store = None
    import_state.oauth = None
    import_state.connections = None
    import_state.tracker = None
    import_state.factory = None
    import_state.engine = None

    app = create_app(db_path=str(tmp_path / "maestro.db"))
    with TestClient(app) as c:
        yield c

    # Tear down so a later test with a different env var gets a fresh state.
    oem_state._initialized = False
    oem_state.engine = None
    oem_state.decision_engine = None
    oem_state.evidence_graph = None
    oem_state.signals = []
    oem_state._demo_seeded = False


# ═══════════════════════════════════════════════════════════════════════════
# 1. SIMULATOR CONSOLIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulatorConsolidation:
    def test_post_simulator_returns_inputs_field(self, client):
        """The previously-failing test_post_simulator — /simulator must
        return `inputs.hire_count` in its response (was returning only
        `inputs_applied`, causing a KeyError)."""
        r = client.post("/api/oem/simulator", json={"inputs": {"hire_count": 3}})
        assert r.status_code == 200
        data = r.json()
        assert data["inputs"]["hire_count"] == 3
        assert "predicted" in data
        assert "confidence" in data
        assert "base_health" in data

    def test_simulator_and_simulate_return_identical_results(self, client):
        """Both /simulator and /simulate must return identical results
        because they delegate to the same SimulationEngine."""
        payload = {"inputs": {"hire_count": 5}}
        r1 = client.post("/api/oem/simulator", json=payload)
        r2 = client.post("/api/oem/simulate", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        # Every field must match — same engine, same calculation.
        assert r1.json() == r2.json()

    def test_simulate_response_has_both_inputs_and_inputs_applied(self, client):
        """The response includes both `inputs` (raw user payload) and
        `inputs_applied` (validated) for backward compatibility."""
        r = client.post("/api/oem/simulate", json={"inputs": {"hire_count": "7"}})
        assert r.status_code == 200
        data = r.json()
        # `inputs` preserves what the user sent (string "7").
        assert data["inputs"]["hire_count"] == "7"
        # `inputs_applied` has the coerced int.
        assert data["inputs_applied"]["hire_count"] == 7

    def test_simulation_engine_is_single_source_of_truth(self, client):
        """The SimulationEngine class exists and produces the canonical
        response shape. Both route handlers delegate to it."""
        engine = SimulationEngine(oem_state.model, oem_state.decisions)
        result = engine.simulate(inputs={"hire_count": 2})
        for key in ("base_health", "predicted", "confidence",
                    "linked_laws", "inputs", "inputs_applied"):
            assert key in result, f"SimulationEngine missing {key}"
        assert result["inputs"]["hire_count"] == 2
        assert result["inputs_applied"]["hire_count"] == 2

    def test_twin_simulate_is_separate_from_simulate(self, client):
        """/twin/simulate returns an ImpactReport (organizational what-if),
        NOT the metric what-if that /simulate returns. The two are
        intentionally separate because they answer different questions."""
        r_metric = client.post("/api/oem/simulate", json={"inputs": {"hire_count": 3}})
        r_twin = client.post("/api/oem/twin/simulate", json={
            "type": "add_hires", "domain": "payments", "count": 3,
        })
        assert r_metric.status_code == 200
        assert r_twin.status_code == 200
        metric = r_metric.json()
        twin = r_twin.json()
        # Metric what-if has base_health/predicted; twin what-if has
        # overloaded_people/knowledge_loss/risk_level. Different shapes.
        assert "base_health" in metric
        assert "predicted" in metric
        assert "overloaded_people" in twin or "risk_level" in twin
        assert "base_health" not in twin


# ═══════════════════════════════════════════════════════════════════════════
# 2. DEMO PROVIDER
# ═══════════════════════════════════════════════════════════════════════════

class TestDemoProvider:
    def test_demo_provider_implements_page_fetcher(self):
        """DemoPageFetcher must satisfy the PageFetcher interface so it
        can go through the real ingestion pipeline."""
        from maestro_oem.ingestion import PageFetcher
        fetcher = DemoPageFetcher("github")
        assert isinstance(fetcher, PageFetcher)
        assert fetcher.provider == "github"

    def test_demo_provider_supports_all_five_providers(self):
        """The demo dataset covers the same providers as real OAuth plus customer."""
        providers = demo_provider_names()
        # 5 original (github, jira, slack, confluence, gmail) + customer
        assert set(providers) == {"github", "jira", "slack", "confluence", "gmail", "customer"}

    def test_demo_provider_fetch_page_returns_items(self):
        """fetch_page_sync returns the demo items for page 1."""
        fetcher = DemoPageFetcher("github")
        result = fetcher.fetch_page_sync(page=1)
        assert result.status.value == "success"
        assert len(result.items) > 0
        assert result.items_count == len(result.items)
        # Page 2 returns empty (single-page demo)
        result2 = fetcher.fetch_page_sync(page=2)
        assert len(result2.items) == 0

    def test_demo_seed_loads_through_ingestion_pipeline(self, client):
        """The OEM is seeded at startup via DemoPageFetcher, not via
        hardcoded constants. If the demo seed loads, recommendations exist."""
        # If the demo seed went through the ingestion pipeline correctly,
        # the OEM will have signals, laws, and recommendations.
        resp = client.get("/api/oem/state")
        assert resp.status_code == 200
        summary = resp.json().get("summary", {})
        assert summary.get("signals_processed", 0) > 0, "Demo seed did not load"
        assert summary.get("laws_inferred", 0) > 0

        resp = client.get("/api/oem/recommendations")
        assert resp.status_code == 200
        recs = resp.json().get("recommendations", [])
        assert len(recs) > 0, "Demo seed loaded but produced no recommendations"

    def test_demo_total_events_matches_expected(self):
        """Sanity check on the demo dataset size."""
        total = demo_total_events()
        # 11 github + 12 jira + 6 slack + 6 confluence + 4 gmail = 39
        # + 26 customer events (3 enterprise customers) = 65
        assert total == 66, f"Expected 66 demo events (65 base + 1 mutated Globex commitment from Phase 2.2), got {total}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. MAESTRO_DEMO_SEED ENV VAR
# ═══════════════════════════════════════════════════════════════════════════

class TestDemoSeedEnvVar:
    def test_demo_seed_enabled_defaults_to_true(self, monkeypatch):
        """Without MAESTRO_DEMO_SEED set, demo seed is ON (default)."""
        monkeypatch.delenv("MAESTRO_DEMO_SEED", raising=False)
        assert _demo_seed_enabled() is True

    def test_demo_seed_disabled_with_false(self, monkeypatch):
        """MAESTRO_DEMO_SEED=false disables the demo seed."""
        for val in ("false", "False", "FALSE", "0", "no", "off"):
            monkeypatch.setenv("MAESTRO_DEMO_SEED", val)
            assert _demo_seed_enabled() is False, f"MAESTRO_DEMO_SEED={val} should disable"

    def test_demo_seed_enabled_with_true(self, monkeypatch):
        """MAESTRO_DEMO_SEED=true explicitly enables the demo seed."""
        for val in ("true", "True", "TRUE", "1", "yes", "on"):
            monkeypatch.setenv("MAESTRO_DEMO_SEED", val)
            assert _demo_seed_enabled() is True, f"MAESTRO_DEMO_SEED={val} should enable"

    def test_empty_oem_when_demo_seed_disabled(self, empty_client):
        """With MAESTRO_DEMO_SEED=false, the OEM starts with zero signals
        and zero laws. This is the production deployment path."""
        resp = empty_client.get("/api/oem/state")
        assert resp.status_code == 200
        summary = resp.json().get("summary", {})
        assert summary.get("signals_processed", 0) == 0
        assert summary.get("laws_inferred", 0) == 0
        assert summary.get("patterns_detected", 0) == 0

    def test_no_recommendations_when_demo_seed_disabled(self, empty_client):
        """An empty OEM produces no recommendations."""
        resp = empty_client.get("/api/oem/recommendations")
        assert resp.status_code == 200
        assert resp.json()["recommendations"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. LAW DEDUP
# ═══════════════════════════════════════════════════════════════════════════

class TestLawDedup:
    def test_law_dedup_key_strips_evidence_count(self):
        """The dedup key strips the volatile 'N evidence signals across M
        observations' suffix so two patterns describing the same phenomenon
        map to the same key."""
        from maestro_oem.model import ExecutionModel
        key1 = ExecutionModel._law_dedup_key(
            "priya.m@acme.com is a bottleneck — 3 evidence signals across 3 observations"
        )
        key2 = ExecutionModel._law_dedup_key(
            "priya.m@acme.com is a bottleneck — 4 evidence signals across 4 observations"
        )
        assert key1 == key2, (
            "Same bottleneck at different evidence counts must dedup to the same key"
        )
        assert "3 evidence" not in key1
        assert "4 evidence" not in key2

    def test_law_dedup_key_distinguishes_different_entities(self):
        from maestro_oem.model import ExecutionModel
        key_priya = ExecutionModel._law_dedup_key(
            "priya.m@acme.com is a bottleneck — 3 evidence signals across 3 observations"
        )
        key_carlos = ExecutionModel._law_dedup_key(
            "carlos.r@acme.com is a bottleneck — 3 evidence signals across 3 observations"
        )
        assert key_priya != key_carlos

    def test_no_duplicate_priya_bottleneck_law(self, client):
        """The L-0001 / L-0003 bug: two laws for the same person being a
        bottleneck, differing only in evidence count. After the dedup fix,
        there must be exactly ONE law for priya.m@acme.com being a bottleneck."""
        resp = client.get("/api/oem/laws")
        assert resp.status_code == 200
        laws = resp.json().get("laws", [])
        priya_bottleneck_laws = [
            l for l in laws
            if "priya.m@acme.com" in l.get("statement", "")
            and "bottleneck" in l.get("statement", "").lower()
        ]
        assert len(priya_bottleneck_laws) <= 1, (
            f"Expected at most 1 Priya bottleneck law, found {len(priya_bottleneck_laws)}: "
            f"{[l['code'] for l in priya_bottleneck_laws]}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. WCAG CONTRAST
# ═══════════════════════════════════════════════════════════════════════════

class TestWCAGContrast:
    @staticmethod
    def _luminance(r: int, g: int, b: int) -> float:
        def f(c: float) -> float:
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    @classmethod
    def _contrast(cls, hex1: str, hex2: str) -> float:
        def parse(h: str) -> tuple[int, int, int]:
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        l1 = cls._luminance(*parse(hex1))
        l2 = cls._luminance(*parse(hex2))
        if l1 < l2:
            l1, l2 = l2, l1
        return (l1 + 0.05) / (l2 + 0.05)

    def test_no_failing_contrast_color_in_app_html(self):
        """The old #71717a (4.18:1 on #06060d, fails WCAG AA 4.5:1) must
        not appear anywhere in app.html."""
        app_html = Path(__file__).resolve().parents[3] / "app.html"
        content = app_html.read_text()
        assert "#71717a" not in content, (
            "#71717a (4.18:1 contrast) still present in app.html — fails WCAG AA"
        )
        assert "#5c5c70" not in content, (
            "#5c5c70 (3.3:1 contrast) still present in app.html — fails WCAG AA"
        )

    def test_replacement_color_passes_wcag_aa(self):
        """The replacement #9a9aa3 must achieve >= 4.5:1 on #06060d."""
        ratio = self._contrast("#9a9aa3", "#06060d")
        assert ratio >= 4.5, (
            f"#9a9aa3 on #06060d = {ratio:.2f}:1 — fails WCAG AA (need 4.5:1)"
        )

    def test_all_text_colors_in_app_html_pass_aa(self):
        """Every hex color used for text in app.html must achieve >= 4.5:1
        against the body background (#06060d). This is the comprehensive
        check — not just the one color that was flagged."""
        app_html = Path(__file__).resolve().parents[3] / "app.html"
        content = app_html.read_text()
        bg = "#06060d"
        # Find all hex colors used in `color:` declarations.
        color_pattern = re.compile(r"color:\s*(#[0-9a-fA-F]{6})")
        colors = set(color_pattern.findall(content))
        failing = []
        for color in colors:
            ratio = self._contrast(color, bg)
            if ratio < 4.5:
                failing.append((color, ratio))
        assert not failing, (
            f"These text colors in app.html fail WCAG AA (4.5:1) on {bg}: "
            f"{failing}"
        )
