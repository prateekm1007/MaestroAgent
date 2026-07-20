"""
S2-05b regression test: structural joke detection.

Verifies that riddle/rhetorical-question patterns are NOT classified as
commitments, even when they contain "I promise" or "I will".

The auditor's riddle: "Why did the chicken cross the road? I promise it
was to get to the other side." was classified as a real commitment
because the existing joke detection only checked for slang markers
(haha, lol, etc.) — not structural joke patterns (riddle format).

Tests the S2-05b fix: structural joke detection BEFORE the LLM path.
"""
import sys
import pytest
import asyncio
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "maestro-personal" / "src"))
sys.path.insert(0, str(REPO / "backend"))

from maestro_personal_shell.commitment_classifier import classify_commitment


@pytest.mark.asyncio
async def test_riddle_not_classified_as_commitment():
    """The auditor's riddle must NOT be classified as a commitment."""
    riddle = "Why did the chicken cross the road? I promise it was to get to the other side."
    result = await classify_commitment(riddle)
    assert not result["is_commitment"], \
        f"Riddle was classified as a commitment: {result}"
    assert result["commitment_type"] == "not_a_commitment"


@pytest.mark.asyncio
async def test_slang_joke_not_classified_as_commitment():
    """Slang jokes (haha, lol) must NOT be classified as commitments."""
    joke = "I promise I will become a billionaire tomorrow, haha."
    result = await classify_commitment(joke)
    assert not result["is_commitment"], \
        f"Slang joke was classified as a commitment: {result}"


@pytest.mark.asyncio
async def test_real_commitment_still_works():
    """Real commitments must still be classified correctly."""
    real = "I promise to send Alex the pricing deck by Friday."
    result = await classify_commitment(real)
    assert result["is_commitment"], \
        f"Real commitment was rejected: {result}"


@pytest.mark.asyncio
async def test_question_then_promise_pattern():
    """Question-then-promise patterns must NOT be classified as commitments."""
    joke = "What do you call a fake noodle? I will tell you — an impasta."
    result = await classify_commitment(joke)
    assert not result["is_commitment"], \
        f"Question-then-promise joke was classified as a commitment: {result}"
