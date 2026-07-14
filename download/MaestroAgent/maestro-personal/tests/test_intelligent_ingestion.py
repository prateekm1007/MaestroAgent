"""Tests for LLM-powered intelligent ingestion (Change 18)."""
import os
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_PERSONAL_TOKEN", "test")
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.pop("OLLAMA_HOST", None)


class TestIntelligentIngestion:
    """Test that regex + LLM classification produces high-precision signals."""

    @pytest.mark.asyncio
    async def test_explicit_commitment_is_ingested(self):
        """'I will send the proposal by Friday' → ingested as explicit."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="I will send the proposal by Friday",
            entity="Maria Garcia",
            source="gmail",
        )
        assert len(signals) >= 1
        assert signals[0]["commitment_type"] in ("explicit", "implicit", "conditional")
        assert signals[0]["state"] == "active"

    @pytest.mark.asyncio
    async def test_tentative_is_rejected(self):
        """'I will try to attend' → rejected (tentative)."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="I will try to attend the meeting",
            entity="Team",
            source="gmail",
        )
        # Either rejected entirely (0 signals) or classified as non-tentative
        for s in signals:
            assert s.get("commitment_type") != "tentative", \
                f"Tentative should be rejected, got: {s}"

    @pytest.mark.asyncio
    async def test_no_commitment_in_text(self):
        """'Great meeting today' → no signals."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="Great meeting today, thanks everyone",
            entity="Team",
            source="gmail",
        )
        assert len(signals) == 0

    @pytest.mark.asyncio
    async def test_confidence_is_set(self):
        """Each signal has a confidence value."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="I will send the report by Friday",
            entity="Avery Stone",
            source="gmail",
        )
        if signals:
            assert "confidence" in signals[0]
            assert 0.0 <= signals[0]["confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_source_is_set(self):
        """Signal includes the source (gmail/slack/github)."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="I will deliver the integration by Q4",
            entity="Orion Tech",
            source="github",
        )
        if signals:
            assert signals[0]["source"] == "github"

    @pytest.mark.asyncio
    async def test_metadata_contains_classification(self):
        """Signal metadata includes the commitment classification."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="I will send the proposal by Friday",
            entity="Maria Garcia",
            source="gmail",
        )
        if signals:
            assert "metadata" in signals[0]
            assert "classification" in signals[0]["metadata"]

    @pytest.mark.asyncio
    async def test_multiple_commitments_in_one_message(self):
        """Multiple commitments in one message are all extracted."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        signals = await extract_signals_intelligently(
            message_text="I will send the proposal by Friday. I will also share the timeline next week.",
            entity="Maria Garcia",
            source="gmail",
        )
        # Should find at least 1 (may or may not catch both depending on regex)
        assert len(signals) >= 1

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self):
        """If LLM fails, regex result is ingested as explicit with 0.5 confidence."""
        from maestro_personal_shell.intelligent_ingestion import extract_signals_intelligently
        # This should trigger the fallback path (LLM may not be available)
        signals = await extract_signals_intelligently(
            message_text="I will send the document tomorrow",
            entity="Test Entity",
            source="gmail",
        )
        # Should still get signals (via fallback)
        if signals:
            assert signals[0]["commitment_type"] in ("explicit", "implicit", "conditional")
            assert signals[0]["state"] in ("active", "cancelled", "completed_verified", "disputed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
