"""M4 fix — User-friendly terminology translation for API responses.

M4 from adversarial audit at f16cf66:
> "Evidence Spine", "Organizational Laws", "Learning Objects" appear in
> API responses. May be exposed to users via frontend. Internal terminology
> should not leak into customer experience.
> Fix: Translate internal terms to user-friendly language in API responses.

This module provides a single function: translate_internal_terms() that
takes a dict/list/str and replaces internal terminology with user-friendly
equivalents. Applied at the API response boundary, it prevents internal
architecture terms from leaking into the customer experience.

Translation map (internal → user-friendly):
  - "Evidence Spine" → "Supporting Evidence"
  - "evidence_spine" → "supporting_evidence" (key form)
  - "Organizational Laws" / "organizational law" → "Operating Principles"
  - "Learning Objects" / "learning object" → "Patterns & Insights"
  - "learning_objects" / "learning_object" → "patterns" (key form)
  - "OEM" (as standalone) → "Maestro" (in user-facing strings only)

Usage in routes:
    from maestro_oem.terminology_translation import translate_internal_terms
    return translate_internal_terms(result_dict)

The translation is applied recursively to dict keys + string values.
Lists are traversed. Non-string values are passed through unchanged.
"""

from __future__ import annotations

from typing import Any

# ─── Translation map ────────────────────────────────────────────────────
# Internal term → user-friendly term.
# Keys are matched case-insensitively in string values.
# Dict keys are matched exactly (snake_case stays snake_case).

_TERM_TRANSLATIONS = {
    # Full phrases (matched in string values, case-insensitive)
    "Evidence Spine": "Supporting Evidence",
    "evidence spine": "Supporting Evidence",
    "Organizational Laws": "Operating Principles",
    "organizational laws": "Operating Principles",
    "organizational law": "Operating Principle",
    "Learning Objects": "Patterns & Insights",
    "learning objects": "Patterns & Insights",
    "learning object": "Pattern",
    # Standalone "OEM" → "Maestro" only when it appears as a standalone word
    # (not part of an identifier like OEMEngine or oem_state)
    # This is handled specially in _translate_string to avoid breaking code.
}

# Dict key translations (exact match only — these are snake_case API keys)
_KEY_TRANSLATIONS = {
    "evidence_spine": "supporting_evidence",
    "learning_objects": "patterns",
    "learning_object": "pattern",
    # Note: "laws" stays "laws" — it's already user-friendly enough
    # Note: "organizational_law" is rare as a key; if it appears, translate it
    "organizational_law": "operating_principle",
    "organizational_laws": "operating_principles",
}


def translate_internal_terms(obj: Any) -> Any:
    """Recursively translate internal terminology in a response object.

    Args:
        obj: A dict, list, string, or other value. Non-string non-container
            values are returned unchanged.

    Returns:
        A new object with internal terms translated to user-friendly language.
        The input object is not mutated.

    Example:
        >>> translate_internal_terms({"evidence_spine": "The Evidence Spine shows..."})
        {'supporting_evidence': 'The Supporting Evidence shows...'}
    """
    if isinstance(obj, dict):
        return {
            _translate_key(k): translate_internal_terms(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [translate_internal_terms(item) for item in obj]
    if isinstance(obj, str):
        return _translate_string(obj)
    return obj


def _translate_key(key: str) -> str:
    """Translate a dict key if it's in the internal-term key map."""
    return _KEY_TRANSLATIONS.get(key, key)


def _translate_string(s: str) -> str:
    """Translate internal terms in a string value.

    Matches case-insensitively for phrases. Preserves the rest of the
    string. "OEM" is only translated when it appears as a standalone word
    (not part of OEMEngine, oem_state, etc.).
    """
    result = s
    # Apply phrase translations (case-insensitive)
    for internal, friendly in _TERM_TRANSLATIONS.items():
        # Case-insensitive replacement
        import re
        # Use word boundaries for phrases to avoid partial matches
        pattern = re.compile(re.escape(internal), re.IGNORECASE)
        result = pattern.sub(friendly, result)

    # Special handling for standalone "OEM" → "Maestro"
    # Only replace when OEM appears as a standalone word (not part of an identifier)
    import re
    # \b OEM \b but NOT when preceded/followed by alphanumeric (which would
    # indicate it's part of an identifier like OEMEngine or oem_state)
    result = re.sub(r'\bOEM\b(?!Engine|State|Store|Registry)', 'Maestro', result)

    return result


def get_translation_map() -> dict[str, str]:
    """Return the translation map for inspection/testing."""
    return {
        "phrases": dict(_TERM_TRANSLATIONS),
        "keys": dict(_KEY_TRANSLATIONS),
    }
