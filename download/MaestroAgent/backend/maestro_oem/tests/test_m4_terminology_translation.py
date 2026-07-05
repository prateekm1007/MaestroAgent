"""M4 fix — Terminology translation test (P22).

M4 from adversarial audit at f16cf66:
> "Evidence Spine", "Organizational Laws", "Learning Objects" appear in
> API responses. Internal terminology should not leak into customer experience.
> Fix: Translate internal terms to user-friendly language in API responses.

This test verifies by execution that:
1. translate_internal_terms() translates all known internal phrases
2. Dict keys are translated (evidence_spine → supporting_evidence, etc.)
3. String values are translated (case-insensitive)
4. Lists are traversed recursively
5. Non-string values (int, bool, None) pass through unchanged
6. "OEM" as a standalone word → "Maestro" (but OEMEngine/oem_state preserved)
7. The helper is importable from the production path

This is P22: the test executes the actual translation function, not a mock.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def test_translate_evidence_spine_phrase():
    """M4 fix: 'Evidence Spine' → 'Supporting Evidence'."""
    from maestro_oem.terminology_translation import translate_internal_terms

    assert translate_internal_terms("The Evidence Spine shows...") == "The Supporting Evidence shows..."
    assert translate_internal_terms("evidence spine") == "Supporting Evidence"
    assert translate_internal_terms("EVIDENCE SPINE") == "Supporting Evidence"


def test_translate_organizational_laws_phrase():
    """M4 fix: 'Organizational Laws' → 'Operating Principles'."""
    from maestro_oem.terminology_translation import translate_internal_terms

    assert translate_internal_terms("Organizational Laws are rules.") == "Operating Principles are rules."
    assert translate_internal_terms("organizational law") == "Operating Principle"


def test_translate_learning_objects_phrase():
    """M4 fix: 'Learning Objects' → 'Patterns & Insights'."""
    from maestro_oem.terminology_translation import translate_internal_terms

    assert translate_internal_terms("Learning Objects detected") == "Patterns & Insights detected"
    assert translate_internal_terms("learning object") == "Pattern"


def test_translate_dict_keys():
    """M4 fix: dict keys are translated (snake_case → user-friendly snake_case)."""
    from maestro_oem.terminology_translation import translate_internal_terms

    result = translate_internal_terms({
        "evidence_spine": {"claim": "test"},
        "learning_objects": 5,
        "learning_object": {"id": "lo-1"},
        "organizational_law": "L-0001",
        "organizational_laws": ["L-0001", "L-0002"],
    })

    assert "evidence_spine" not in result, "evidence_spine key must be translated"
    assert "supporting_evidence" in result, "evidence_spine → supporting_evidence"
    assert "learning_objects" not in result, "learning_objects key must be translated"
    assert "patterns" in result, "learning_objects → patterns"
    assert "learning_object" not in result
    assert "pattern" in result, "learning_object → pattern"
    assert "organizational_law" not in result
    assert "operating_principle" in result
    assert "organizational_laws" not in result
    assert "operating_principles" in result


def test_translate_nested_structures():
    """M4 fix: translation is recursive (dicts in lists in dicts)."""
    from maestro_oem.terminology_translation import translate_internal_terms

    result = translate_internal_terms({
        "whispers": [
            {"evidence_spine": "The Evidence Spine for Globex"},
            {"learning_objects": [{"title": "Learning Object: pricing"}]},
        ],
        "summary": "Organizational Laws: 3, Learning Objects: 5",
    })

    # Nested dict key translated
    assert "supporting_evidence" in result["whispers"][0]
    assert "evidence_spine" not in result["whispers"][0]
    # Nested string value translated
    assert "Supporting Evidence" in result["whispers"][0]["supporting_evidence"]
    # Deeply nested key translated
    assert "patterns" in result["whispers"][1]
    # Summary string translated
    assert "Operating Principles" in result["summary"]
    assert "Patterns & Insights" in result["summary"]
    assert "Organizational Laws" not in result["summary"]
    assert "Learning Objects" not in result["summary"]


def test_non_string_values_pass_through():
    """M4 fix: non-string values (int, bool, None) pass through unchanged."""
    from maestro_oem.terminology_translation import translate_internal_terms

    result = translate_internal_terms({
        "count": 42,
        "active": True,
        "metadata": None,
        "ratio": 0.85,
    })

    assert result["count"] == 42
    assert result["active"] is True
    assert result["metadata"] is None
    assert result["ratio"] == 0.85


def test_oem_standalone_translated_but_identifiers_preserved():
    """M4 fix: standalone 'OEM' → 'Maestro', but OEMEngine/oem_state preserved.

    The regex uses \\bOEM\\b(?!Engine|State|Store|Registry) to avoid
    breaking identifiers like OEMEngine, oem_state, OEMStore.
    """
    from maestro_oem.terminology_translation import translate_internal_terms

    # Standalone OEM → Maestro
    assert translate_internal_terms("The OEM is running") == "The Maestro is running"
    assert translate_internal_terms("OEM status: OK") == "Maestro status: OK"

    # OEMEngine preserved (not translated)
    assert "OEMEngine" in translate_internal_terms("OEMEngine started")
    assert "MaestroEngine" not in translate_internal_terms("OEMEngine started")

    # oem_state preserved (lowercase, part of identifier)
    result = translate_internal_terms("oem_state initialized")
    assert "oem_state" in result
    assert "maestro_state" not in result


def test_empty_and_no_match_strings():
    """M4 fix: empty strings and strings without internal terms pass through."""
    from maestro_oem.terminology_translation import translate_internal_terms

    assert translate_internal_terms("") == ""
    assert translate_internal_terms("Hello world") == "Hello world"
    assert translate_internal_terms("No internal terms here") == "No internal terms here"


def test_translation_map_is_inspectable():
    """M4 fix: get_translation_map() returns the map for inspection."""
    from maestro_oem.terminology_translation import get_translation_map

    tm = get_translation_map()
    assert "phrases" in tm
    assert "keys" in tm
    assert "Evidence Spine" in tm["phrases"]
    assert tm["phrases"]["Evidence Spine"] == "Supporting Evidence"
    assert "evidence_spine" in tm["keys"]
    assert tm["keys"]["evidence_spine"] == "supporting_evidence"


def test_simulated_api_response_translation():
    """M4 fix: a simulated API response with internal terms is fully translated.

    P22: this test simulates what the /api/oem/whisper endpoint returns
    and verifies all internal terms are translated.
    """
    from maestro_oem.terminology_translation import translate_internal_terms

    # Simulated whisper response (shape matches real /api/oem/whisper output)
    response = {
        "insight": "Globex SSO commitment at risk",
        "evidence_spine": {
            "claim": "The Evidence Spine shows Globex was promised SSO",
            "observed_facts": [
                {"source": "slack", "text": "Organizational Laws require delivery"},
                {"source": "email", "text": "Learning Objects detected about pricing"},
            ],
        },
        "learning_objects": [
            {"id": "lo-1", "title": "Learning Object: delivery trust"},
        ],
        "summary": "OEM detected 3 Organizational Laws and 5 Learning Objects",
        "count": 5,
    }

    translated = translate_internal_terms(response)

    # No internal terms remain
    response_str = str(translated)
    assert "Evidence Spine" not in response_str, "Evidence Spine must be translated"
    assert "Organizational Laws" not in response_str, "Organizational Laws must be translated"
    assert "Learning Objects" not in response_str, "Learning Objects must be translated"
    assert "evidence_spine" not in response_str, "evidence_spine key must be translated"
    assert "learning_objects" not in response_str, "learning_objects key must be translated"

    # User-friendly terms present
    assert "Supporting Evidence" in response_str
    assert "Operating Principles" in response_str
    assert "Patterns & Insights" in response_str
    assert "supporting_evidence" in response_str
    assert "patterns" in response_str

    # Non-string values preserved
    assert translated["count"] == 5


if __name__ == "__main__":
    test_translate_evidence_spine_phrase()
    print("PASS: test_translate_evidence_spine_phrase")
    test_translate_organizational_laws_phrase()
    print("PASS: test_translate_organizational_laws_phrase")
    test_translate_learning_objects_phrase()
    print("PASS: test_translate_learning_objects_phrase")
    test_translate_dict_keys()
    print("PASS: test_translate_dict_keys")
    test_translate_nested_structures()
    print("PASS: test_translate_nested_structures")
    test_non_string_values_pass_through()
    print("PASS: test_non_string_values_pass_through")
    test_oem_standalone_translated_but_identifiers_preserved()
    print("PASS: test_oem_standalone_translated_but_identifiers_preserved")
    test_empty_and_no_match_strings()
    print("PASS: test_empty_and_no_match_strings")
    test_translation_map_is_inspectable()
    print("PASS: test_translation_map_is_inspectable")
    test_simulated_api_response_translation()
    print("PASS: test_simulated_api_response_translation")
    print("\nAll M4 terminology translation tests passed.")
