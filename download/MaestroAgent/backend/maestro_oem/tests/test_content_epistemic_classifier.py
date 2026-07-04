"""Priority 4: Content-level epistemic classification — analyze the actual
text, not just the signal type.

The prior adversarial audit found (H-02):
> Epistemic classification is signal-type-driven, not content-driven. A
> "proposal" in a commitment signal becomes a "commitment." No NLP/LLM
> classification of actual statement intent.

The current EvidenceBuilder sets claim_type based on the whisper type:
  - commitment whisper → claim_type="commitment"
  - objection whisper → claim_type="observed_fact"
  - broken commitment → claim_type="outcome"

This is wrong. The claim_type should reflect the EPISTEMIC nature of the
statement, not the signal type it arrived in:
  - "We will deliver SSO by Q4" → commitment (a promise)
  - "We should support SSO" → proposal (a suggestion, NOT a promise)
  - "Engineering thinks SSO can be ready by Q4" → estimate (human-reported forecast)
  - "If we prioritize SSO, TestCorp will renew" → hypothesis (conditional falsifiable)
  - "The release will likely slip" → prediction (system-generated forecast)
  - "The release failed Tuesday" → observed_fact (directly witnessed)
  - "Engineering believes Legal caused the delay" → reported_statement

The fix: ContentEpistemicClassifier analyzes the actual text and returns
the epistemic type. The EvidenceBuilder uses this classifier's output
instead of hardcoding claim_type per whisper type.

Design:
  - Rule-based now (regex + keywords), LLM-ready later
  - Conservative: when uncertain, default to the signal-type-based type
    (backward-compatible). Content classification only OVERRIDES when
    confident.
  - The classifier never SILENCES evidence (P6) — it only relabels.

Adversarial tests (write first, watch fail, then fix):

  1. test_content_classifier_exists
     ContentEpistemicClassifier must exist and be importable.

  2. test_classify_commitment
     "We will deliver SSO by Q4" → "commitment"

  3. test_classify_proposal
     "We should support SSO" → "proposal" (NOT "commitment")

  4. test_classify_estimate
     "Engineering thinks SSO can be ready by Q4" → "estimate"

  5. test_classify_hypothesis
     "If we prioritize SSO, TestCorp will renew" → "hypothesis"

  6. test_classify_prediction
     "The release will likely slip" → "prediction"

  7. test_classify_observed_fact
     "The release failed Tuesday" → "observed_fact"

  8. test_classify_reported_statement
     "Engineering believes Legal caused the delay" → "reported_statement"

  9. test_evidence_builder_uses_content_classifier
     EvidenceBuilder must use ContentEpistemicClassifier to set claim_type
     based on the actual commitment text, not just the whisper type.

  10. test_proposal_in_commitment_signal_classified_as_proposal
      VERIFICATION GATE: A signal typed CUSTOMER_COMMITMENT_MADE but with
      text "we should support SSO" must produce evidence with
      claim_type="proposal", NOT "commitment".

  11. test_wiring_p11_classifier_in_evidence_py
      P11: evidence.py must reference ContentEpistemicClassifier.

  12. test_classifier_backward_compat
      When the classifier is uncertain (no clear pattern), it returns
      the fallback type (the signal-type-based type). This preserves
      backward compatibility.

  13. test_classifier_never_silences
      The classifier only relabels claim_type — it never causes evidence
      to be dropped or suppressed (P6).

P2: Untested code is unverified code.
P6: Fail-closed — classifier only relabels, never silences.
P11: Wiring proved by grep + execution.
P13: Epistemic type is DERIVED from content, not caller-supplied.
"""
from __future__ import annotations

import sys
import inspect
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ═══ Priority 4: Content-level epistemic classification ════════════════════

# ─── 1. ContentEpistemicClassifier exists ──────────────────────────────────

def test_content_classifier_exists():
    """ContentEpistemicClassifier must exist and be importable."""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    assert ContentEpistemicClassifier is not None


# ─── 2. Classify commitment ────────────────────────────────────────────────

def test_classify_commitment():
    """'We will deliver SSO by Q4' → 'commitment'"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("We will deliver SSO by Q4", fallback="commitment")
    assert result == "commitment", (
        f"'We will deliver SSO by Q4' must classify as commitment. Got: {result}"
    )


# ─── 3. Classify proposal ──────────────────────────────────────────────────

def test_classify_proposal():
    """'We should support SSO' → 'proposal' (NOT 'commitment')"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("We should support SSO", fallback="commitment")
    assert result == "proposal", (
        f"'We should support SSO' must classify as proposal, NOT commitment. Got: {result}"
    )


# ─── 4. Classify estimate ──────────────────────────────────────────────────

def test_classify_estimate():
    """'Engineering thinks SSO can be ready by Q4' → 'estimate'"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("Engineering thinks SSO can be ready by Q4", fallback="inference")
    assert result == "estimate", (
        f"'Engineering thinks SSO can be ready by Q4' must classify as estimate. Got: {result}"
    )


# ─── 5. Classify hypothesis ────────────────────────────────────────────────

def test_classify_hypothesis():
    """'If we prioritize SSO, TestCorp will renew' → 'hypothesis'"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("If we prioritize SSO, TestCorp will renew", fallback="prediction")
    assert result == "hypothesis", (
        f"'If we prioritize SSO, TestCorp will renew' must classify as hypothesis. Got: {result}"
    )


# ─── 6. Classify prediction ────────────────────────────────────────────────

def test_classify_prediction():
    """'The release will likely slip' → 'prediction'"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("The release will likely slip", fallback="inference")
    assert result == "prediction", (
        f"'The release will likely slip' must classify as prediction. Got: {result}"
    )


# ─── 7. Classify observed_fact ─────────────────────────────────────────────

def test_classify_observed_fact():
    """'The release failed Tuesday' → 'observed_fact'"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("The release failed Tuesday", fallback="observed_fact")
    assert result == "observed_fact", (
        f"'The release failed Tuesday' must classify as observed_fact. Got: {result}"
    )


# ─── 8. Classify reported_statement ────────────────────────────────────────

def test_classify_reported_statement():
    """'Engineering believes Legal caused the delay' → 'reported_statement'"""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    result = classifier.classify("Engineering believes Legal caused the delay", fallback="inference")
    assert result == "reported_statement", (
        f"'Engineering believes Legal caused the delay' must classify as reported_statement. Got: {result}"
    )


# ─── 9. EvidenceBuilder uses content classifier ───────────────────────────

def test_evidence_builder_uses_content_classifier():
    """EvidenceBuilder must use ContentEpistemicClassifier to set claim_type
    based on the actual commitment text, not just the whisper type."""
    from maestro_oem import evidence
    source = inspect.getsource(evidence)
    assert "ContentEpistemicClassifier" in source or "content_epistemic_classifier" in source, (
        "evidence.py must reference ContentEpistemicClassifier (P11 — wired into EvidenceBuilder)"
    )


# ─── 10. VERIFICATION GATE: proposal in commitment signal ─────────────────

def test_proposal_in_commitment_signal_classified_as_proposal():
    """VERIFICATION GATE: A signal typed CUSTOMER_COMMITMENT_MADE but with
    text 'we should support SSO' must produce evidence with
    claim_type='proposal', NOT 'commitment'."""
    from maestro_oem.evidence import EvidenceBuilder
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider

    # A signal typed as commitment, but the text is a proposal
    sig = ExecutionSignal(
        type=SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane@example.com",
        artifact="crm:1",
        metadata={"customer": "TestCorp", "commitment": "We should support SSO"},
        provider=SignalProvider.CUSTOMER,
    )
    builder = EvidenceBuilder([sig])
    evidence = builder.build_for_whisper(
        whisper_type="commitment_exists",
        entity="TestCorp",
        topic="",
        raw_evidence={"artifact": "crm:1", "timestamp": sig.timestamp.isoformat()},
        context="meeting",
    )
    assert evidence.claim_type == "proposal", (
        f"A commitment signal with proposal text ('we should support SSO') must "
        f"be classified as 'proposal', NOT 'commitment'. Got: {evidence.claim_type}"
    )


# ─── 11. P11: classifier referenced in evidence.py ─────────────────────────

def test_wiring_p11_classifier_in_evidence_py():
    """P11: evidence.py must reference ContentEpistemicClassifier."""
    from maestro_oem import evidence
    source = inspect.getsource(evidence)
    assert "ContentEpistemicClassifier" in source, (
        "evidence.py must reference ContentEpistemicClassifier (P11 — wired into production)"
    )


# ─── 12. Backward compat: uncertain → fallback ─────────────────────────────

def test_classifier_backward_compat():
    """When the classifier is uncertain (no clear pattern), it returns
    the fallback type (the signal-type-based type). This preserves
    backward compatibility."""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    # Ambiguous text — no clear epistemic marker
    result = classifier.classify("The meeting happened", fallback="observed_fact")
    assert result == "observed_fact", (
        f"Uncertain text must fall back to the provided type. Got: {result}"
    )


# ─── 13. Classifier never silences (P6) ────────────────────────────────────

def test_classifier_never_silences():
    """The classifier only relabels claim_type — it never causes evidence
    to be dropped or suppressed (P6)."""
    from maestro_oem.content_epistemic_classifier import ContentEpistemicClassifier
    classifier = ContentEpistemicClassifier()
    # Even with a relabel, the classifier returns a valid claim_type string
    for text in [
        "We will deliver SSO by Q4",
        "We should support SSO",
        "Engineering thinks SSO can be ready by Q4",
        "If we prioritize SSO, TestCorp will renew",
        "The release will likely slip",
        "The release failed Tuesday",
        "Engineering believes Legal caused the delay",
        "The meeting happened",  # ambiguous
    ]:
        result = classifier.classify(text, fallback="observed_fact")
        assert isinstance(result, str) and len(result) > 0, (
            f"Classifier must always return a non-empty string. Got: {result!r} for text: {text!r}"
        )
        # Must be one of the 10 valid epistemic types
        valid_types = {
            "observed_fact", "reported_statement", "commitment", "assumption",
            "inference", "prediction", "outcome", "proposal", "estimate", "hypothesis",
        }
        assert result in valid_types, (
            f"Classifier must return a valid epistemic type. Got: {result!r} for text: {text!r}"
        )
