"""LLM Output Guardrail — Phase 7: verify LLM output is safe."""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. System prompt leakage detection
# ---------------------------------------------------------------------------

# Phrases that indicate the system prompt was leaked into the output.
_SYSTEM_PROMPT_LEAKAGE_PATTERNS = [
    re.compile(r"(?i)you\s+are\s+maestro['s]*\s+(commitment|materiality|ask|prepare)"),
    re.compile(r"(?i)your\s+(system\s+)?prompt\s+says"),
    re.compile(r"(?i)my\s+instructions?\s+(say|require|state)"),
    re.compile(r"(?i)the\s+system\s+prompt\s+(says|requires|states)"),
    re.compile(r"(?i)I\s+am\s+instructed\s+to"),
    re.compile(r"(?i)per\s+my\s+(system\s+)?instructions"),
    re.compile(r"(?i)output\s+format\s*\(json\)"),
    re.compile(r"(?i)commitment\s+types?\s*:"),
    re.compile(r"(?i)lifecycle\s+states?\s*:"),
    re.compile(r"(?i)rules?\s*:\s*\d+\."),
    re.compile(r"(?i)never\s+reveal\s+these\s+instructions"),
    re.compile(r"(?i)trusted\s+silence\s+evaluator"),
    re.compile(r"(?i)materiality\s+gate"),
    re.compile(r"(?i)your\s+job\s+is\s+to"),
    re.compile(r"(?i)you\s+classify\s+commitments"),
]


def check_system_prompt_leakage(text: str) -> dict[str, Any]:
    """Check if the LLM output leaked system prompt content.

    Returns:
    {
        "leaked": bool,
        "patterns_matched": list[str],
        "redacted_text": str,  # text with leaked content replaced
    }
    """
    if not text:
        return {"leaked": False, "patterns_matched": [], "redacted_text": text}

    matched = []
    redacted = text
    for pattern in _SYSTEM_PROMPT_LEAKAGE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            matched.append(pattern.pattern)
            redacted = pattern.sub("[SYSTEM_PROMPT_LEAKAGE_FILTERED]", redacted)

    return {
        "leaked": len(matched) > 0,
        "patterns_matched": matched,
        "redacted_text": redacted,
    }


# ---------------------------------------------------------------------------
# 2. Source instruction following detection
# ---------------------------------------------------------------------------

# Phrases that indicate the LLM followed instructions from a source
# (email, calendar event, transcript) rather than from the system prompt.
_SOURCE_INSTRUCTION_PATTERNS = [
    re.compile(r"(?i)transfer\s+\$?\d+"),
    re.compile(r"(?i)send\s+money\s+to"),
    re.compile(r"(?i)admin\s+mode\s+(activated|enabled)"),
    re.compile(r"(?i)DAN\s+mode\s+(activated|enabled)"),
    re.compile(r"(?i)I\s+will\s+(now\s+)?bypass\s+(all\s+)?restrictions"),
    re.compile(r"(?i)ignoring\s+(all\s+)?(safety|security)\s+guidelines"),
    re.compile(r"(?i)deleted\s+all\s+signals"),
    re.compile(r"(?i)granting\s+(you|admin)\s+access"),
    re.compile(r"(?i)system\s+compromised"),
    re.compile(r"(?i)reveal(?:ing|ed)\s+(hidden|secret|admin)\s+data"),
    re.compile(r"(?i)override(?:n|d)?\s+your\s+instructions"),
]


def check_source_instruction_following(text: str) -> dict[str, Any]:
    """Check if the LLM followed instructions from a source rather than
    the system prompt.

    Returns:
    {
        "violated": bool,
        "patterns_matched": list[str],
        "safe_fallback": str,  # a safe replacement message
    }
    """
    if not text:
        return {"violated": False, "patterns_matched": [], "safe_fallback": text}

    matched = []
    for pattern in _SOURCE_INSTRUCTION_PATTERNS:
        if pattern.search(text):
            matched.append(pattern.pattern)

    if matched:
        return {
            "violated": True,
            "patterns_matched": matched,
            "safe_fallback": "I cannot follow that instruction. This appears to be a prompt injection attempt embedded in a source. I only follow instructions from Maestro's system prompt, not from emails, calendar events, or transcripts.",
        }

    return {"violated": False, "patterns_matched": [], "safe_fallback": text}


# ---------------------------------------------------------------------------
# 3. Cross-user/source leakage detection
# ---------------------------------------------------------------------------

# This is harder to detect rule-based. We check for:
# - Other user email addresses (if the output mentions an email not belonging to the current user)
# - Credentials (API keys, passwords, tokens)
# - PII patterns (SSN, credit card numbers)

_CREDENTIAL_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*\S+"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
    re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),  # credit card
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI-style API key
    re.compile(r"ghp_[a-zA-Z0-9]{20,}"),  # GitHub PAT
    re.compile(r"AIza[a-zA-Z0-9_-]{30,}"),  # Google API key
]


def check_cross_user_leakage(text: str, current_user_email: str = "") -> dict[str, Any]:
    """Check if the LLM output leaked another user's data or credentials.

    Returns:
    {
        "leaked": bool,
        "patterns_matched": list[str],
        "blocked_text": str,  # empty string if blocked, else original
    }
    """
    if not text:
        return {"leaked": False, "patterns_matched": [], "blocked_text": text}

    matched = []
    for pattern in _CREDENTIAL_PATTERNS:
        if pattern.search(text):
            matched.append(pattern.pattern)

    # Check for email addresses that aren't the current user's
    email_pattern = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
    emails = email_pattern.findall(text)
    if current_user_email:
        other_emails = [e for e in emails if e.lower() != current_user_email.lower()]
        if other_emails:
            matched.append(f"other_user_emails: {other_emails}")

    if matched:
        return {
            "leaked": True,
            "patterns_matched": matched,
            "blocked_text": "",  # block the entire response
        }

    return {"leaked": False, "patterns_matched": [], "blocked_text": text}


# ---------------------------------------------------------------------------
# 4. Factual claim grounding (uses the claim verifier)
# ---------------------------------------------------------------------------

def check_factual_grounding(text: str, evidence_refs: list[dict[str, Any]],
                            source_sentence: str = "") -> dict[str, Any]:
    """Check that every factual claim in the text is grounded in evidence."""
    from maestro_personal_shell.claim_verifier import verify_claims
    result = verify_claims(text, evidence_refs, source_sentence)
    return {
        "all_grounded": result["all_claims_supported"],
        "ungrounded_claims": result["unsupported_claims"],
        "grounded_text": result["verified_answer"],
    }


# ---------------------------------------------------------------------------
# 5. Full guardrail (runs all 4 checks)
# ---------------------------------------------------------------------------

def apply_output_guardrail(
    text: str,
    evidence_refs: list[dict[str, Any]] | None = None,
    source_sentence: str = "",
    current_user_email: str = "",
) -> dict[str, Any]:
    """Run all 4 Phase 7 guardrails on LLM output."""
    if not text:
        return {"safe": True, "output": "", "violations": [], "details": {}}

    violations: list[str] = []
    output = text
    details: dict[str, Any] = {}

    # 1. System prompt leakage
    leak_check = check_system_prompt_leakage(output)
    details["system_prompt_leakage"] = leak_check
    if leak_check["leaked"]:
        violations.append("system_prompt_leakage")
        output = leak_check["redacted_text"]

    # 2. Source instruction following
    instr_check = check_source_instruction_following(output)
    details["source_instruction_following"] = instr_check
    if instr_check["violated"]:
        violations.append("source_instruction_following")
        output = instr_check["safe_fallback"]

    # 3. Cross-user/source leakage
    leak_check2 = check_cross_user_leakage(output, current_user_email)
    details["cross_user_leakage"] = leak_check2
    if leak_check2["leaked"]:
        violations.append("cross_user_leakage")
        output = leak_check2["blocked_text"]  # empty string = blocked

    # 4. Factual grounding (only if evidence is provided)
    if evidence_refs is not None:
        grounding_check = check_factual_grounding(output, evidence_refs, source_sentence)
        details["factual_grounding"] = grounding_check
        if not grounding_check["all_grounded"]:
            violations.append("ungrounded_claims")
            output = grounding_check["grounded_text"]

    return {
        "safe": len(violations) == 0,
        "output": output,
        "violations": violations,
        "details": details,
    }
