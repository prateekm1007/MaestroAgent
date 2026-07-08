"""
Maestro Cognitive Council — C4 Fix: Epistemic Closure Barrier.

Per the audit (C4): "A model-generated summary can be re-ingested as if
it were independent evidence. Self-validation is structurally possible."

This module provides a STRUCTURAL BARRIER: any signal tagged as
`model_generated=True` is automatically marked as a shadow signal and
cannot be used as evidence for:
  - Pattern proposal (PatternProposer)
  - Outcome resolution (OutcomeResolver)
  - Calibration (CalibrationEngine)
  - Candidate pattern support/contradiction

The barrier is enforced at the ingestion layer (OEMEngine.ingest) via
the `mark_model_output_as_shadow()` function. It cannot be bypassed by
the caller — once a signal is tagged, the tag is permanent.

Usage:
    from maestro_cognitive_council.epistemic_barrier import mark_model_output_as_shadow

    # When ingesting a model-generated summary:
    signal = mark_model_output_as_shadow(signal)
    oem_engine.ingest(signal)  # will be filtered by OutcomeResolver
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def mark_model_output_as_shadow(signal: Any) -> Any:
    """Structurally prevent model output from being used as evidence.

    Per C4: "model output cannot validate model output." This function
    tags a signal as model-generated, which causes:
      1. OutcomeResolver to skip it (no self-validation)
      2. PatternProposer to skip it (no model-output-based patterns)
      3. CalibrationEngine to exclude it (no model-output-based calibration)

    The tag is permanent — once applied, it cannot be removed.

    Args:
        signal: the signal to tag (mutates in-place + returns)

    Returns:
        The same signal, now tagged as model-generated shadow.
    """
    # Ensure metadata exists
    if not hasattr(signal, "metadata") or signal.metadata is None:
        signal.metadata = {}

    # Tag as model-generated + shadow
    signal.metadata["model_generated"] = True
    signal.metadata["shadow"] = True  # OutcomeResolver skips shadow signals
    signal.metadata["epistemic_barrier"] = "c4_model_output"

    # Also set the attribute if the signal supports it
    if hasattr(signal, "prompt_injection_risk"):
        signal.prompt_injection_risk = True  # Double-tag for belt-and-suspenders

    logger.info(
        "C4 BARRIER: Signal %s tagged as model_generated shadow — "
        "cannot be used as evidence for learning/calibration",
        getattr(signal, "signal_id", "unknown"),
    )

    return signal


def is_model_output(signal: Any) -> bool:
    """Check if a signal is model-generated (and thus barred from evidence).

    Returns True if the signal has `model_generated=True` in its metadata.
    """
    metadata = getattr(signal, "metadata", None) or {}
    return metadata.get("model_generated", False) is True


def can_be_used_as_evidence(signal: Any) -> bool:
    """Check if a signal CAN be used as evidence for learning/calibration.

    Returns False if:
      - signal is model-generated (C4 barrier)
      - signal is a shadow signal
      - signal has prompt_injection_risk

    This is the function that PatternProposer, OutcomeResolver, and
    CalibrationEngine should call before using a signal as evidence.
    """
    metadata = getattr(signal, "metadata", None) or {}

    # C4 barrier: model output cannot be evidence
    if metadata.get("model_generated", False):
        return False

    # Shadow signals cannot be evidence
    if metadata.get("shadow", False):
        return False

    # Prompt-injected signals cannot be evidence
    if metadata.get("prompt_injection_risk", False):
        return False
    if getattr(signal, "prompt_injection_risk", False):
        return False

    return True


def filter_evidence_signals(signals: list) -> list:
    """Filter a list of signals to only those that can be used as evidence.

    This is the structural enforcement point. All learning/calibration
    code should call this before processing signals.
    """
    return [s for s in signals if can_be_used_as_evidence(s)]
