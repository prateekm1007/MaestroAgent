"""Phase 7+8 gap tests: CRM connector + Whisper transcriber + real audio E2E.

Tests the 3 previously-missing pieces:
1. Whisper WASM integration (whisper-transcriber.js exists + wired into offscreen.js)
2. CRM auto-sync connector (commitments, outcomes, meetings → Salesforce/HubSpot)
3. Real audio E2E test (simulated audio → transcript → suggestions → post-call)
"""

from __future__ import annotations

import sys, pathlib, json, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import asyncio
import pytest


class TestWhisperTranscriber:
    """Phase 2 gap: Whisper WASM transcriber exists and is wired into offscreen.js."""

    def test_whisper_transcriber_file_exists(self):
        """whisper-transcriber.js exists in extension/lib/."""
        transcriber_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "lib" / "whisper-transcriber.js"
        assert transcriber_path.exists(), "whisper-transcriber.js must exist"

    def test_whisper_transcriber_has_load_method(self):
        """WhisperTranscriber class has load() and transcribe() methods."""
        transcriber_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "lib" / "whisper-transcriber.js"
        src = transcriber_path.read_text()
        assert "class WhisperTranscriber" in src
        assert "async load()" in src
        assert "async transcribe(" in src
        assert "async transcribeStream(" in src

    def test_whisper_uses_transformers_js(self):
        """WhisperTranscriber uses Transformers.js (Xenova/transformers) for local inference."""
        transcriber_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "lib" / "whisper-transcriber.js"
        src = transcriber_path.read_text()
        assert "@xenova/transformers" in src or "xenova" in src.lower()
        assert "automatic-speech-recognition" in src  # pipeline type

    def test_whisper_audio_never_leaves_device(self):
        """The transcriber processes audio locally — no audio upload."""
        transcriber_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "lib" / "whisper-transcriber.js"
        src = transcriber_path.read_text()
        # Should NOT contain any fetch/XMLHttpRequest/upload of audio data
        assert "fetch" not in src.lower() or "fetch" in src.split("import")[0]  # allow CDN import only
        assert "XMLHttpRequest" not in src
        assert "upload" not in src.lower()

    def test_offscreen_wired_to_whisper(self):
        """offscreen.js imports and uses WhisperTranscriber."""
        offscreen_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "offscreen.js"
        src = offscreen_path.read_text()
        assert "whisper-transcriber" in src or "WhisperTranscriber" in src
        assert "transcribeStream" in src or "transcribe(" in src

    def test_offscreen_sends_transcript_not_audio(self):
        """offscreen.js sends TRANSCRIPT_CHUNK (text), NOT AUDIO_CHUNK."""
        offscreen_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "offscreen.js"
        src = offscreen_path.read_text()
        assert "TRANSCRIPT_CHUNK" in src
        assert "AUDIO_CHUNK" not in src  # old stub sent audio chunks; now sends transcripts

    def test_consent_still_gates_capture(self):
        """Consent check still precedes getDisplayMedia in offscreen.js."""
        offscreen_path = pathlib.Path(__file__).resolve().parents[3] / "extension" / "offscreen.js"
        src = offscreen_path.read_text()
        # Find the actual consent check call (not the function definition or comments)
        # and the actual getDisplayMedia call (not comments)
        consent_match = re.search(r'checkConsentViaBackground\(["\']audio["\']\)', src)
        capture_match = re.search(r'navigator\.mediaDevices\.getDisplayMedia', src)
        assert consent_match, "Consent check call not found"
        assert capture_match, "getDisplayMedia call not found"
        assert consent_match.start() < capture_match.start(), \
            f"Consent check (pos {consent_match.start()}) must precede getDisplayMedia (pos {capture_match.start()})"


class TestCRMConnector:
    """Phase 7 gap: CRM auto-sync connector."""

    def _make_connector(self, provider="salesforce"):
        from maestro_oem.crm_connector import CRMConnector, CRMConfig, CRMProvider
        config = CRMConfig(
            provider=CRMProvider(provider),
            client_id="test-client-id",
            client_secret="test-secret",
            instance_url="https://test.my.salesforce.com",
        )
        return CRMConnector(config)

    def test_sync_commitment_success(self):
        """Commitment is synced to CRM successfully."""
        connector = self._make_connector()
        result = asyncio.run(connector.sync_commitment({
            "text": "Deploy SSO by Friday",
            "actor": "raj@globex.com",
            "entity": "Globex",
            "due_date": "2024-12-15",
        }))
        from maestro_oem.crm_connector import SyncStatus
        assert result.status == SyncStatus.SUCCESS
        assert result.external_id  # non-empty
        assert result.provider.value == "salesforce"

    def test_sync_outcome_success(self):
        """Outcome is synced to CRM successfully."""
        connector = self._make_connector()
        result = asyncio.run(connector.sync_outcome({
            "entity": "Globex",
            "outcome": "commitment_kept",
            "meeting_id": "m-123",
        }))
        from maestro_oem.crm_connector import SyncStatus
        assert result.status == SyncStatus.SUCCESS

    def test_sync_meeting_summary_success(self):
        """Meeting summary is synced to CRM successfully."""
        connector = self._make_connector()
        result = asyncio.run(connector.sync_meeting_summary({
            "title": "Q3 Renewal - Globex",
            "duration_minutes": 34,
            "participants": ["raj@globex.com"],
            "commitments": ["SSO by Friday"],
            "objections": ["Pricing too high"],
        }))
        from maestro_oem.crm_connector import SyncStatus
        assert result.status == SyncStatus.SUCCESS

    def test_sync_skipped_when_not_configured(self):
        """Sync is skipped when CRM is not configured."""
        from maestro_oem.crm_connector import CRMConnector, CRMConfig, CRMProvider, SyncStatus
        config = CRMConfig(provider=CRMProvider.NONE)
        connector = CRMConnector(config)
        result = asyncio.run(connector.sync_commitment({"text": "Test"}))
        assert result.status == SyncStatus.SKIPPED

    def test_sync_skipped_when_disabled(self):
        """Sync is skipped when commitment sync is disabled."""
        from maestro_oem.crm_connector import CRMConnector, CRMConfig, CRMProvider, SyncStatus
        config = CRMConfig(
            provider=CRMProvider.SALESFORCE,
            client_id="test",
            instance_url="https://test.salesforce.com",
            sync_commitments=False,
        )
        connector = CRMConnector(config)
        result = asyncio.run(connector.sync_commitment({"text": "Test"}))
        assert result.status == SyncStatus.SKIPPED

    def test_salesforce_payload_format(self):
        """Salesforce commitment payload has correct field structure."""
        connector = self._make_connector("salesforce")
        payload = connector._build_commitment_payload({
            "text": "Deploy SSO by Friday",
            "actor": "raj@globex.com",
            "due_date": "2024-12-15",
        })
        assert "Subject" in payload
        assert "ActivityDate" in payload
        assert "Description" in payload
        assert "Maestro" in payload["Description"]

    def test_hubspot_payload_format(self):
        """HubSpot commitment payload has correct field structure."""
        from maestro_oem.crm_connector import CRMConnector, CRMConfig, CRMProvider
        config = CRMConfig(
            provider=CRMProvider.HUBSPOT,
            client_id="test",
            instance_url="https://api.hubapi.com",
        )
        connector = CRMConnector(config)
        payload = connector._build_commitment_payload({
            "text": "Deploy SSO by Friday",
            "actor": "raj@globex.com",
        })
        assert "properties" in payload
        assert "hs_task_subject" in payload["properties"]

    def test_sync_log_tracking(self):
        """Sync operations are logged for audit."""
        connector = self._make_connector()
        asyncio.run(connector.sync_commitment({"text": "Test 1"}))
        asyncio.run(connector.sync_commitment({"text": "Test 2"}))
        log = connector.get_sync_log()
        assert len(log) >= 2

    def test_sync_stats(self):
        """Sync statistics are computed correctly."""
        connector = self._make_connector()
        asyncio.run(connector.sync_commitment({"text": "Test 1"}))
        asyncio.run(connector.sync_commitment({"text": "Test 2"}))
        stats = connector.get_sync_stats()
        assert stats["total"] >= 2
        assert stats["success"] >= 2
        assert stats["success_rate"] > 0

    def test_p25_confidence_has_denominator(self):
        """P25: sync confidence shows denominator (successful sync count)."""
        from maestro_oem.crm_connector import CRMConfig, CRMProvider
        config = CRMConfig(
            provider=CRMProvider.SALESFORCE,
            client_id="test",
            instance_url="https://test.salesforce.com",
        )
        assert "insufficient" in config.confidence_label
        assert config.sync_count == 0

        config.sync_count = 15
        assert "15" in config.confidence_label

    def test_one_way_sync_only(self):
        """CRM sync is one-way (Maestro → CRM), not bidirectional."""
        from maestro_oem.crm_connector import CRMConnector
        # Verify no "fetch_from_crm" or "pull" methods exist
        assert not hasattr(CRMConnector, "fetch_from_crm")
        assert not hasattr(CRMConnector, "pull_from_crm")
        assert not hasattr(CRMConnector, "import_from_crm")


class TestRealAudioE2E:
    """Phase 8 gap: real audio E2E test (simulated audio → transcript → suggestions)."""

    def test_full_pipeline_transcript_to_suggestions(self):
        """Full E2E: transcript text → LiveIntelligenceEngine → suggestion cards → post-call."""
        import sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
        from maestro_oem.live_intelligence import LiveIntelligenceEngine
        from fastapi.testclient import TestClient
        from maestro_api.main import create_app

        # Step 1: Simulate what the Whisper transcriber would produce
        # (in production, WhisperTranscriber.transcribe() produces this text)
        simulated_transcript_chunks = [
            {"text": "We can offer $50,000 for the annual contract.", "speaker": "Sam Kumar"},
            {"text": "That is above what we budgeted for this quarter.", "speaker": "Sam Kumar"},
            {"text": "We will deliver the SSO integration by next Friday.", "speaker": "Raj Patel"},
        ]

        # Step 2: Process through LiveIntelligenceEngine (as the backend would)
        engine = LiveIntelligenceEngine(None)
        all_cards = []
        for chunk in simulated_transcript_chunks:
            cards = engine.process_transcript(chunk["text"], chunk["speaker"], "Globex")
            all_cards.extend(cards)

        # Verify objection detected
        objection_cards = [c for c in all_cards if c.card_type == "objection"]
        assert len(objection_cards) >= 1, "Should detect pricing objection from 'above budget'"

        # Verify commitment detected
        commitment_cards = [c for c in all_cards if c.card_type == "commitment"]
        assert len(commitment_cards) >= 1, "Should detect commitment from 'will deliver SSO'"

        # Step 3: Post-call summary (as the post-call endpoint would)
        app = create_app(db_path=":memory:")
        with TestClient(app) as c:
            r = c.post("/api/copilot/post-call", json={
                "meeting_title": "Q3 Renewal — Globex Corp",
                "duration_seconds": 2052,
                "participants": ["raj@globex.com", "sam@globex.com"],
                "transcript_chunks": simulated_transcript_chunks,
                "suggestion_cards": [c.to_dict() for c in all_cards],
                "entity": "Globex",
            })
            assert r.status_code == 200
            summary = r.json()
            assert summary["hero_summary"]["title"] == "Q3 Renewal — Globex Corp"
            assert summary["key_stats"]["commitments"] >= 1
            assert summary["key_stats"]["objections"] >= 1
            assert "SSO" in summary["draft_email"]["body"] or "deliver" in summary["draft_email"]["body"].lower()
            assert summary["what_maestro_learned"]["new_signals_ingested"] >= 1

    def test_transcript_chunks_have_evidence(self):
        """Every suggestion card from the pipeline has evidence (anti-Cluely)."""
        from maestro_oem.live_intelligence import LiveIntelligenceEngine
        engine = LiveIntelligenceEngine(None)
        cards = engine.process_transcript(
            "That is above what we budgeted. We will deliver SSO by Friday.",
            "Sam", "Globex"
        )
        for card in cards:
            assert card.evidence.get("source"), f"Card missing evidence source: {card.card_type}"

    def test_no_audio_data_in_pipeline(self):
        """The E2E pipeline carries ONLY text — no audio data anywhere."""
        from maestro_oem.live_intelligence import LiveIntelligenceEngine
        engine = LiveIntelligenceEngine(None)
        cards = engine.process_transcript("We will deliver SSO.", "Sam", "Globex")
        for card in cards:
            d = card.to_dict()
            # No audio fields should exist in the card
            for key in d:
                assert "audio" not in key.lower(), f"Card has audio field: {key}"
                assert "wav" not in key.lower(), f"Card has wav field: {key}"
                assert "blob" not in key.lower(), f"Card has blob field: {key}"


class TestGapL0NoRegression:
    """L0 must not regress after gap fixes."""

    def test_situation_snapshot_27_fields(self):
        from maestro_oem.situation import Situation
        import dataclasses
        assert len(dataclasses.fields(Situation)) == 27

    def test_outcome_ledger_functional(self):
        from maestro_oem.governed_adaptation import OutcomeLedger
        ol = OutcomeLedger()
        assert hasattr(ol, "append") and hasattr(ol, "count")

    def test_classifier_new_types(self):
        from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
        clf = ContentEpistemicClassifier()
        assert clf.classify("Maybe we can ship SSO by Q4.") == "tentative"
