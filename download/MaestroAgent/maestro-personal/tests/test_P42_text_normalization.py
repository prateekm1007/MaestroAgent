"""P42 — Text normalization before structural matching.

Anti-apostrophe-defeat: the tentative filter missed
"I will try to get it done, but dont count on it" because the hedge check
matched "don't" but the text had "dont" — an apostrophe defeated the
rules engine. P42: normalize ONCE, check many. Never duplicate
contraction variants in keyword lists.

This test file verifies:
1. normalize_text() expands the 10 canonical contractions correctly.
2. _rule_based_classify() correctly classifies "dont count on it" (no
   apostrophe) as tentative — the original failure case.
3. The classifier does NOT mis-classify "I will send the proposal" as
   tentative (regression — "i'll" must not be confused with "ill").

Run:
  cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal
  python -m pytest tests/test_P42_text_normalization.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")


from maestro_personal_shell.commitment_classifier import normalize_text, _rule_based_classify


# ---------------------------------------------------------------------------
# 1. normalize_text — 10 canonical contractions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("don't", "do not"),
    ("cant", "cannot"),  # no apostrophe — must still normalize
    ("I'll", "i will"),
    ("won't", "will not"),
    ("don't count on it", "do not count on it"),  # the auditor's exact case
    ("they're", "they are"),
    ("isn't", "is not"),
    ("wouldnt", "would not"),  # no apostrophe — common misspelling
    ("let's", "let us"),
    ("that's", "that is"),
])
def test_normalize_text_contraction_expansion(raw, expected):
    """P42: each contraction maps to its expanded form (apostrophe or not)."""
    assert normalize_text(raw) == expected, (
        f"P42 violation: normalize_text({raw!r}) returned {normalize_text(raw)!r}, "
        f"expected {expected!r}. The contraction map is incomplete or misordered."
    )


def test_normalize_text_preserves_internal_punctuation():
    """Internal punctuation like dashes is preserved (only contractions expanded)."""
    assert "—" in normalize_text("I will try — but dont count on it")
    assert normalize_text("Hello, World!") == "hello, world!"


def test_normalize_text_lowercases_and_collapses_whitespace():
    """Lowercase + collapse whitespace."""
    assert normalize_text("  DON'T   COUNT   ON  IT  ") == "do not count on it"


def test_normalize_text_empty():
    """Empty input returns empty."""
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


# ---------------------------------------------------------------------------
# 2. _rule_based_classify — the original failure case is now classified correctly
# ---------------------------------------------------------------------------

def test_dont_count_on_it_is_tentative_NO_apostrophe():
    """P42 journey: 'dont count on it' (no apostrophe) → tentative, NOT a commitment.

    This is THE case the auditor identified: an apostrophe defeated the rules
    engine. With normalization, 'dont' → 'do not' → matches 'do not count on'.
    """
    result = _rule_based_classify("I will try to get it done, but dont count on it")
    assert result["commitment_type"] == "tentative", (
        f"Expected tentative, got {result['commitment_type']}. "
        f"P42 fix not applied — apostrophe-defeat persists."
    )
    assert result["is_commitment"] is False


def test_dont_count_on_it_with_apostrophe_also_tentative():
    """P42 regression: 'don't count on it' (with apostrophe) still tentative."""
    result = _rule_based_classify("I will try to get it done, but don't count on it")
    assert result["commitment_type"] == "tentative"
    assert result["is_commitment"] is False


def test_cant_guarantee_is_NOT_a_commitment_NO_apostrophe():
    """P42: 'cant guarantee' (no apostrophe) → NOT a commitment.

    After normalization, 'cant' → 'cannot' which matches the negation check.
    The classifier returns 'negation' (also non-commitment) instead of
    'tentative' — both correctly exclude from /api/commitments. The
    principle being tested is that the no-apostrophe form is correctly
    normalized and rejected, not the specific subtype.
    """
    result = _rule_based_classify("I will send it, but cant guarantee the timing")
    assert result["is_commitment"] is False, (
        f"P42 fix not applied — 'cant' was not normalized. "
        f"Got is_commitment={result['is_commitment']}, type={result['commitment_type']}."
    )
    assert result["commitment_type"] in ("tentative", "negation"), (
        f"Expected tentative or negation, got {result['commitment_type']}"
    )


def test_ill_try_is_tentative_WITH_apostrophe():
    """P42: "I'll try" (with apostrophe) → tentative.

    Note: 'Ill' (no apostrophe) is NOT normalized because it's ambiguous
    (could be the medical condition). The apostrophe form is unambiguous.
    """
    result = _rule_based_classify("I'll try to get it done")
    assert result["commitment_type"] == "tentative", (
        f"Expected tentative, got {result['commitment_type']}"
    )
    assert result["is_commitment"] is False


def test_explicit_commitment_NOT_misclassified_as_tentative():
    """P42 regression: 'I will send the proposal' (no hedge) → explicit, NOT tentative."""
    result = _rule_based_classify("I will send the proposal by Friday")
    assert result["commitment_type"] == "explicit", (
        f"Expected explicit, got {result['commitment_type']} — "
        f"normalization may have broken the explicit keyword match."
    )
    assert result["is_commitment"] is True


def test_explicit_with_apostrophe_still_explicit():
    """P42 regression: 'I'll send the proposal' (with apostrophe) → explicit."""
    result = _rule_based_classify("I'll send the proposal by Friday")
    assert result["commitment_type"] == "explicit"
    assert result["is_commitment"] is True


def test_negation_wont_is_negation_NO_apostrophe():
    """P42: 'wont' (no apostrophe) → negation."""
    result = _rule_based_classify("I wont send the report")
    assert result["commitment_type"] == "negation"
    assert result["is_commitment"] is False


def test_implicit_im_on_it_is_implicit_WITH_apostrophe():
    """P42: "i'm on it" (with apostrophe) → implicit commitment.

    Note: 'im' (no apostrophe) is NOT normalized because it's ambiguous
    (could be short for "instant message"). The apostrophe form is
    unambiguous.
    """
    result = _rule_based_classify("i'm on it")
    assert result["commitment_type"] == "implicit"
    assert result["is_commitment"] is True


# ---------------------------------------------------------------------------
# 3. P42 anti-duplication — verify the keyword lists no longer have duplicates
# ---------------------------------------------------------------------------

def test_no_duplicate_contraction_variants_in_hedge_markers():
    """P42 structural check: the hedge_markers list should NOT contain both
    'don't count on' and 'dont count on' — normalize_text makes them the same.
    """
    import inspect
    import re as _re
    src = inspect.getsource(_rule_based_classify)
    # Find the hedge_markers list literal
    m = _re.search(r"hedge_markers\s*=\s*\[(.*?)\]", src, _re.DOTALL)
    assert m, "hedge_markers list not found in _rule_based_classify source"
    hedge_list_src = m.group(1)
    # P42 violation: both forms present means the duplication persists
    assert "don't count on" not in hedge_list_src, (
        "P42 violation: hedge_markers still contains 'don\\'t count on' — "
        "normalize_text expands it to 'do not count on'; the apostrophe form "
        "is dead code that signals the duplication smell persists."
    )
    assert "dont count on" not in hedge_list_src, (
        "P42 violation: hedge_markers still contains 'dont count on' — "
        "normalize_text expands it to 'do not count on'; the no-apostrophe "
        "form is dead code that signals the duplication smell persists."
    )
    assert "do not count on" in hedge_list_src, (
        "P42: hedge_markers must contain the canonical normalized form 'do not count on'"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
