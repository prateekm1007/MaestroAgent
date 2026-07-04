"""C4 fix: confidence display gate — gate display on calibration sample size.

External auditor finding (C4): confidence value 0.8484 displayed with
4-decimal precision. The denominator was 0 outcomes. The formula was
correct; the display was dishonest — 4-decimal precision implies a
calibration rigor that 0 outcomes cannot support.

P25: "For every confidence value displayed to the user, the display code
must check the calibration sample size. If the denominator < 10, display
'insufficient calibration history' — never bare 4-decimal precision."

The fix: a helper `format_confidence_for_display(confidence, sample_size)`
that returns either a formatted confidence string (when sample_size >= 10)
or "insufficient calibration history" (when < 10). Wire this into the key
display sites in oem.py.

Adversarial: written FIRST, watched FAIL, then fix applied (P2).
"""
from __future__ import annotations

import sys
import pytest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def test_format_confidence_helper_exists():
    """C4: the format_confidence_for_display helper must exist."""
    from maestro_oem import confidence as conf_module
    assert hasattr(conf_module, "format_confidence_for_display"), \
        "confidence.py must have a format_confidence_for_display helper. " \
        "This is the P25 gate — without it, every display site shows bare 4-decimal precision."


def test_format_confidence_returns_insufficient_for_small_sample():
    """C4 KEY TEST: when sample_size < 10, return 'insufficient calibration history'.

    This is the auditor's exact scenario: 0.8484 confidence with 0 outcomes.
    Before the fix: displayed as 0.8484 (decorative precision).
    After the fix: displayed as 'insufficient calibration history'.
    """
    from maestro_oem.confidence import format_confidence_for_display
    result = format_confidence_for_display(confidence=0.8484, sample_size=0)
    assert "insufficient" in result.lower(), \
        f"With sample_size=0, must return 'insufficient calibration history'. Got: {result!r}"

    result = format_confidence_for_display(confidence=0.8484, sample_size=5)
    assert "insufficient" in result.lower(), \
        f"With sample_size=5 (< 10 threshold), must return 'insufficient'. Got: {result!r}"


def test_format_confidence_returns_value_for_large_sample():
    """C4 counter-test: when sample_size >= 10, return the formatted confidence.

    Non-vacuous: don't gate EVERYTHING — only gate when sample size is too
    small. With 10+ samples, the confidence is meaningful and should display.
    """
    from maestro_oem.confidence import format_confidence_for_display
    result = format_confidence_for_display(confidence=0.8484, sample_size=10)
    assert "insufficient" not in result.lower(), \
        f"With sample_size=10 (>= threshold), must return the confidence value. Got: {result!r}"
    # The helper rounds to 2 decimals for display (0.8484 → 0.85)
    assert "0.85" in result, \
        f"Must include the rounded confidence value (0.8484 → 0.85). Got: {result!r}"


def test_oem_routes_use_format_confidence_for_display():
    """C4: the oem routes must use the helper instead of bare round(confidence, 4).

    Before the fix: 15+ sites in oem.py did `round(confidence, 4)`.
    After the fix: key display sites use format_confidence_for_display with
    the sample size (validated_runtimes + failed_runtimes).
    """
    import inspect
    from maestro_api.routes import oem as oem_module

    source = inspect.getsource(oem_module)
    assert "format_confidence_for_display" in source, \
        "oem.py must use format_confidence_for_display at key display sites. " \
        "Before the C4 fix, all sites used bare round(confidence, 4) with no sample-size gate."
