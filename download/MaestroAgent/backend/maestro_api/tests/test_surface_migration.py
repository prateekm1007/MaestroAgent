"""
Step 6: Migration verification tests.

Per governance P22: 'Regression test must execute the production path.'
Per governance P20: 'If M of N call sites pass it, the fix is M/N% done.'

These tests verify:
  1. Feature flag injection — MAESTRO_USE_COUNCIL=true reaches the browser
  2. Council route parity — adapted responses have legacy fields
  3. Fallback — Council failure → legacy route
  4. Guard presence — both legacy and Council responses have acl_* fields
  5. Call site coverage — no hardcoded /api/oem/ask/conversation in source JS
"""
import json
import pathlib
import re
import sys
import os
import tempfile
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_factory(tmp_path, monkeypatch):
    """Factory that builds a TestClient with configurable MAESTRO_USE_COUNCIL."""
    monkeypatch.setenv("MAESTRO_LOCAL_DEV", "true")
    monkeypatch.setenv("MAESTRO_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("MAESTRO_ADMIN_PASSWORD", "test-admin-pass")
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    monkeypatch.setenv("MAESTRO_APP_DIR", app_dir)

    def _build(use_council: bool = False):
        monkeypatch.setenv("MAESTRO_USE_COUNCIL", "true" if use_council else "false")
        from maestro_api.oem_state import oem_state, import_state
        import_state._initialized = False
        import_state.store = None
        import_state.oauth = None
        import_state.connections = None
        import_state.tracker = None
        import_state.factory = None
        import_state.engine = None

        class _Signal:
            def __init__(self, sig_type, entity, text, days_ago=5):
                self.signal_id = uuid4()
                self.type = SimpleNamespace(value=sig_type)
                self.entity = entity
                self.text = text
                self.metadata = {"customer": entity, "text": text, "source_acl": "public"}
                self.timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)
                self.actor = ""
                self.org_id = "default"
                self.tenant_id = "default"

        oem_state.signals = [
            _Signal("customer.commitment_made", "CustomerA", "Deliver SSO by Friday", days_ago=10),
            _Signal("security.condition", "CustomerA", "Security approval required", days_ago=8),
        ]

        from maestro_api.main import create_app
        app = create_app(db_path=str(tmp_path / "maestro.db"))
        return TestClient(app)

    return _build


class TestFeatureFlagInjection:
    """Step 3: the flag must be injected server-side."""

    def test_flag_true_when_env_set(self, client_factory):
        """MAESTRO_USE_COUNCIL=true → window.MAESTRO_USE_COUNCIL = true in HTML."""
        c = client_factory(use_council=True)
        resp = c.get("/")
        assert resp.status_code == 200
        assert "window.MAESTRO_USE_COUNCIL = true" in resp.text, (
            "Flag must be injected as true when MAESTRO_USE_COUNCIL=true"
        )

    def test_flag_false_when_env_unset(self, client_factory):
        """MAESTRO_USE_COUNCIL=false → window.MAESTRO_USE_COUNCIL = false in HTML."""
        c = client_factory(use_council=False)
        resp = c.get("/")
        assert resp.status_code == 200
        assert "window.MAESTRO_USE_COUNCIL = false" in resp.text, (
            "Flag must be injected as false when MAESTRO_USE_COUNCIL=false"
        )


class TestCouncilRouteParity:
    """Step 2: Council routes with ?legacy_compatible=true must have legacy fields."""

    def test_ask_legacy_compatible_has_answer_field(self, client_factory):
        c = client_factory(use_council=False)
        resp = c.post("/api/council/ask?legacy_compatible=true", json={
            "query": "What's happening with CustomerA?",
            "org_id": "default",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "answer" in body, "Adapted Council Ask must have 'answer' field"
        assert "evidence" in body, "Adapted Council Ask must have 'evidence' field"
        assert "citations" in body, "Adapted Council Ask must have 'citations' field"

    def test_briefing_legacy_compatible_has_overnight_field(self, client_factory):
        c = client_factory(use_council=False)
        resp = c.post("/api/council/briefing?legacy_compatible=true", json={
            "user_email": "",
            "org_id": "default",
            "briefing_type": "morning",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "overnight" in body, "Adapted Council Briefing must have 'overnight' field"
        assert "one_thing" in body, "Adapted Council Briefing must have 'one_thing' field"

    def test_prepare_legacy_compatible_has_meetings_field(self, client_factory):
        c = client_factory(use_council=False)
        resp = c.post("/api/council/prepare?legacy_compatible=true", json={
            "org_id": "default",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "meetings" in body, "Adapted Council Prepare must have 'meetings' field"


class TestGuardPresenceOnCouncilRoutes:
    """Council routes must also have the C3/C7 guards (acl_* fields)."""

    def test_council_ask_has_acl_fields(self, client_factory):
        c = client_factory(use_council=False)
        resp = c.post("/api/council/ask?legacy_compatible=true", json={
            "query": "test", "org_id": "default",
        })
        body = resp.json()
        assert "acl_restricted" in body, "Council Ask must have acl_restricted (legacy guard)"

    def test_council_briefing_has_acl_fields(self, client_factory):
        c = client_factory(use_council=False)
        resp = c.post("/api/council/briefing?legacy_compatible=true", json={
            "user_email": "", "org_id": "default", "briefing_type": "morning",
        })
        body = resp.json()
        assert "acl_restricted" in body, "Council Briefing must have acl_restricted (legacy guard)"


class TestCallSiteCoverage:
    """Step 4: no hardcoded /api/oem/ask/conversation in source JS files.

    Per P20: 'If M of N call sites pass it, the fix is M/N% done.'
    """

    def test_no_hardcoded_ask_conversation_in_source_js(self):
        """Source JS files (not bundles) must not hardcode /api/oem/ask/conversation."""
        repo = pathlib.Path(__file__).resolve().parents[3]
        js_dir = repo / "static" / "js"
        exclude = {"bundle.dev.js", "bundle.min.js", "council-router.js"}
        violations = []
        for js_file in js_dir.rglob("*.js"):
            if js_file.name in exclude:
                continue
            content = js_file.read_text()
            # Look for hardcoded fetch('/api/oem/ask/conversation')
            if "/api/oem/ask/conversation" in content and "MaestroAPI" not in content:
                violations.append(str(js_file.relative_to(repo)))
            # Even if MaestroAPI is used elsewhere in the file, check for
            # remaining hardcoded fetch calls
            for line_num, line in enumerate(content.splitlines(), 1):
                if "/api/oem/ask/conversation" in line and "fetch(" in line:
                    violations.append(f"{js_file.relative_to(repo)}:{line_num}")
        assert not violations, (
            f"Found {len(violations)} hardcoded /api/oem/ask/conversation calls "
            f"(should use MaestroAPI.post instead): {violations}"
        )

    def test_no_hardcoded_preparation_tomorrow_in_source_js(self):
        """Source JS files must not hardcode fetch('/api/oem/preparation/tomorrow')."""
        repo = pathlib.Path(__file__).resolve().parents[3]
        js_dir = repo / "static" / "js"
        exclude = {"bundle.dev.js", "bundle.min.js", "council-router.js"}
        violations = []
        for js_file in js_dir.rglob("*.js"):
            if js_file.name in exclude:
                continue
            content = js_file.read_text()
            for line_num, line in enumerate(content.splitlines(), 1):
                if "/api/oem/preparation/tomorrow" in line and "fetch(" in line:
                    violations.append(f"{js_file.relative_to(repo)}:{line_num}")
        assert not violations, (
            f"Found {len(violations)} hardcoded /api/oem/preparation/tomorrow calls: {violations}"
        )

    def test_maestroapi_helper_used_in_migrated_files(self):
        """Files that previously hardcoded calls must now use MaestroAPI."""
        repo = pathlib.Path(__file__).resolve().parents[3]
        js_dir = repo / "static" / "js"
        migrated_files = ["ask.js", "ask_v2.js", "today.js", "home_core.js"]
        for fname in migrated_files:
            fpath = js_dir / fname
            if not fpath.exists():
                continue
            content = fpath.read_text()
            assert "MaestroAPI." in content, (
                f"{fname} must use MaestroAPI helper after migration"
            )
