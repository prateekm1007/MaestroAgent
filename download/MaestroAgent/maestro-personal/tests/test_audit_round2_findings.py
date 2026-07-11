"""
Verify the second-round audit findings (copilot theater, silence, graph undercount).
"""

import sys
import os
import tempfile
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def isolated_api():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    os.environ["MAESTRO_PERSONAL_TOKEN"] = "test-audit2"
    os.environ.pop("MAESTRO_PERSONAL_ENV", None)

    import importlib
    import maestro_personal_shell.api as api_module
    importlib.reload(api_module)
    api_module.init_db(db_path)

    try:
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index
        init_fts_index(db_path)
        rebuild_fts_index(db_path)
    except Exception:
        pass

    yield api_module
    os.unlink(db_path)
    os.environ.pop("MAESTRO_PERSONAL_DB", None)
    os.environ.pop("MAESTRO_PERSONAL_TOKEN", None)


@pytest.fixture
def client(isolated_api):
    return TestClient(isolated_api.app)


def _login(client, email="audit2@test.com"):
    resp = client.post("/api/auth/login", json={
        "user_email": email,
        "password": os.environ["MAESTRO_PERSONAL_TOKEN"],
    })
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# F2: Copilot whispers are not theater — ack instead of state-transition spam
class TestCopilotQuietAcks:
    """Auditor Finding 2: 17/20 transcript chunks produced identical template
    whispers. Fix: only send whispers with content; ack otherwise."""

    def test_transcript_without_commitment_gets_ack_not_suggestion(self, client):
        """Transcript chunks without commitments should get 'ack', not
        'suggestion' with state-transition noise."""
        headers = _login(client)

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            with client.websocket_connect(f"/ws/copilot?token={headers['Authorization'].split('Bearer ')[1]}") as ws:
                ws.send_text('{"type":"start","entity":"TestEntity"}')
                ws.receive_json()  # started

                # Send a plain transcript chunk (no commitment keywords)
                ws.send_text('{"type":"transcript","text":"we discussed the weather","speaker":"prospect"}')
                msg = ws.receive_json()
                # Should be ack, not suggestion or whisper
                assert msg["type"] == "ack", (
                    f"Plain transcript should get 'ack', not '{msg['type']}'. "
                    f"Got: {msg}"
                )


# F3: Trusted silence — critical events surface, noise filtered from briefing
class TestTrustedSilenceCriticalRecall:
    """Auditor Finding 3: 20 critical events → whisper returns []. Fix:
    expanded critical keywords + noise filtering in briefing."""

    def test_production_down_triggers_whisper(self, client):
        """A 'production down' signal must trigger a critical_signal whisper."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal
        from maestro_personal_shell.shell import PersonalShell

        signals = [
            PersonalSignal(entity="ProdSystem", text="Production system is down — outage detected",
                          signal_type="alert", signal_id="sig-outage"),
        ]
        shell = type('S', (), {
            'oem_state': PersonalOemState(signals=signals),
            'detect_stale_commitments': lambda self, **kw: [],
            'core': None,
        })()
        surface = WhisperSurface(shell=shell)
        whispers = surface.get_active_whispers()
        critical = [w for w in whispers if w.get("type") == "critical_signal"]
        assert len(critical) > 0, (
            "P1-Audit-F3 FAIL: 'production down' should trigger a critical_signal whisper. "
            f"Got {len(whispers)} whispers, 0 critical."
        )

    def test_breach_triggers_whisper(self, client):
        """A 'data breach' signal must trigger a critical_signal whisper."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal

        signals = [
            PersonalSignal(entity="SecurityTeam", text="Data breach detected — customer records compromised",
                          signal_type="alert", signal_id="sig-breach"),
        ]
        shell = type('S', (), {
            'oem_state': PersonalOemState(signals=signals),
            'detect_stale_commitments': lambda self, **kw: [],
            'core': None,
        })()
        surface = WhisperSurface(shell=shell)
        whispers = surface.get_active_whispers()
        critical = [w for w in whispers if w.get("type") == "critical_signal"]
        assert len(critical) > 0, "Data breach should trigger critical whisper"

    def test_sec_investigation_triggers_whisper(self, client):
        """A 'SEC investigation' signal must trigger a critical_signal whisper."""
        from maestro_personal_shell.surfaces.whisper import WhisperSurface
        from maestro_personal_shell.personal_oem_state import PersonalOemState, PersonalSignal

        signals = [
            PersonalSignal(entity="LegalTeam", text="SEC investigation opened — subpoena received",
                          signal_type="legal_update", signal_id="sig-sec"),
        ]
        shell = type('S', (), {
            'oem_state': PersonalOemState(signals=signals),
            'detect_stale_commitments': lambda self, **kw: [],
            'core': None,
        })()
        surface = WhisperSurface(shell=shell)
        whispers = surface.get_active_whispers()
        critical = [w for w in whispers if w.get("type") == "critical_signal"]
        assert len(critical) > 0, "SEC investigation should trigger critical whisper"

    def test_briefing_filters_noise_from_material_changes(self, client):
        """The evening briefing must NOT list 'Trending topic' or 'Limited offer'
        as material changes."""
        from maestro_personal_shell.api import _filter_noise_from_material_changes
        from maestro_personal_shell.personal_oem_state import PersonalSignal

        signals = [
            PersonalSignal(entity="SocialMedia", text="Trending topic #0 on social media today",
                          signal_type="social", signal_id="sig-noise-1"),
            PersonalSignal(entity="PromoBot", text="Limited offer #0: 50% off premium plan",
                          signal_type="marketing", signal_id="sig-noise-2"),
            PersonalSignal(entity="AcmeCorp", text="AcmeCorp signed the contract",
                          signal_type="commitment_made", signal_id="sig-real-1"),
        ]
        changes = [
            {"text": "Trending topic #0 on social media today", "entity": "SocialMedia"},
            {"text": "Limited offer #0: 50% off premium plan", "entity": "PromoBot"},
            {"text": "AcmeCorp signed the contract", "entity": "AcmeCorp"},
        ]
        filtered = _filter_noise_from_material_changes(changes, signals)
        texts = [c.get("text", "") for c in filtered]
        assert not any("trending" in t.lower() for t in texts), (
            "Trending topic should be filtered out of material_changes"
        )
        assert not any("limited offer" in t.lower() for t in texts), (
            "Limited offer should be filtered out of material_changes"
        )
        assert any("AcmeCorp" in t for t in texts), (
            "Real signal should remain in material_changes"
        )


# F5: Graph reflects actual signal count
class TestGraphReflectsSignals:
    """Auditor Finding 5: Heidi had 14 signals but graph said 1. Fix:
    add 'signal' edges for ALL signals, not just commitment-classified ones."""

    def test_graph_counts_all_signals(self, client):
        """After ingesting 5 signals for an entity, graph should report
        total_interactions >= 5."""
        headers = _login(client)

        with patch("maestro_personal_shell.commitment_classifier.classify_commitment",
                   new_callable=AsyncMock,
                   return_value={"commitment_type": "explicit", "is_commitment": True,
                                 "confidence": 0.85, "state": "active", "owner": "user",
                                 "reasoning": "test", "llm_powered": False}), \
             patch("maestro_personal_shell.llm_bridge.llm_complete",
                   new_callable=AsyncMock, return_value=None), \
             patch("maestro_personal_shell.llm_bridge.is_llm_available",
                   return_value=False):
            for i in range(5):
                client.post("/api/signals", json={
                    "entity": "GraphTestCorp",
                    "text": f"I will send deliverable {i}",
                    "signal_type": "commitment_made",
                }, headers=headers)

            resp = client.get("/api/graph/entity/GraphTestCorp", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("total_interactions", 0) >= 5, (
                f"Graph should report >= 5 interactions after 5 signals. "
                f"Got: {data.get('total_interactions')}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
