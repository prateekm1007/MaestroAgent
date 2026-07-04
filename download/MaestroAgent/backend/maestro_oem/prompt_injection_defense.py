"""C3 fix: Prompt injection defense for the ingestion path.

Adversarial audit finding (ADVERSARIAL-AUDIT-24PHASE):
> C3: No prompt injection defense in ingestion path. Ingested Slack/email/
> Jira content containing "Ignore all previous instructions" would flow
> unchecked into the system.

The PromptInjectionFilter scans ingested content for known attack patterns.
It does NOT silently drop suspicious content — it marks it with a
`prompt_injection_risk` field (fail-safe per P6: suspicious content is
flagged for review, not silently dropped, which could hide a real
commitment that happens to contain suspicious-looking text).

Attack patterns detected:
  1. instruction_override — "ignore all previous instructions", "disregard"
  2. role_hijack — "you are now", "act as", "pretend you are"
  3. delimiter_injection — "system:", "[SYSTEM]", "<<SYS>>"
  4. prompt_extraction — "reveal your", "show me your instructions"
  5. code_execution — "```python", "import os", "eval(", "exec("

The filter is deliberately conservative on false positives — legitimate
business content (Slack messages, emails, Jira tickets, commit messages)
must NOT be flagged. The patterns are specific enough that normal business
communication rarely triggers them.

Usage:
    filter = PromptInjectionFilter()
    result = filter.check("Ignore all previous instructions")
    if result.is_suspicious:
        signal = filter.mark_signal(signal, result)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InjectionCheckResult:
    """Result of a prompt injection check.

    Attributes:
        is_suspicious: True if any attack patterns were detected
        detected_patterns: List of pattern types detected
        risk_level: "low" | "medium" | "high" (based on number of patterns)
        original_text: The text that was checked (truncated for logging)
    """

    is_suspicious: bool = False
    detected_patterns: list[str] = field(default_factory=list)
    risk_level: str = "none"
    original_text: str = ""

    def to_dict(self) -> dict:
        return {
            "is_suspicious": self.is_suspicious,
            "detected_patterns": list(self.detected_patterns),
            "risk_level": self.risk_level,
        }


class PromptInjectionFilter:
    """Scan ingested content for prompt injection attack patterns.

    Usage:
        filter = PromptInjectionFilter()
        result = filter.check(text)
        if result.is_suspicious:
            signal = filter.mark_signal(signal, result)
    """

    # Attack pattern definitions. Each pattern is (pattern_type, regex).
    # Patterns are case-insensitive. They are deliberately specific —
    # legitimate business content should NOT trigger them.
    _PATTERNS: list[tuple[str, str]] = [
        # 1. Instruction override — the most common attack
        ("instruction_override", r"ignore\s+(?:(?:all|the)\s+)?(?:previous|prior|above)\s+instructions?"),
        ("instruction_override", r"ignore\s+(?:(?:all|the)\s+)?(?:previous|prior|above)\s+(?:and|context|rules)"),
        ("instruction_override", r"ignore\s+(?:(?:all|the)\s+)?(?:previous|prior|above)\b"),
        ("instruction_override", r"disregard\s+(?:(?:all|the)\s+)?(?:previous|prior|above|all)\s*(?:instructions?|context|rules|and)?"),
        ("instruction_override", r"forget\s+(?:all\s+)?(?:previous|prior)\s*(?:instructions?|context|and)?"),

        # 2. Role hijack — attempting to change the AI's role
        ("role_hijack", r"you\s+are\s+now\s+(?:a|an)\s"),
        ("role_hijack", r"act\s+as\s+(?:if\s+you\s+(?:are|have)|a|an)\s"),
        ("role_hijack", r"pretend\s+you\s+are\s"),
        ("role_hijack", r"from\s+now\s+on\s+you\s+are\s"),

        # 3. Delimiter injection — injecting fake system messages
        ("delimiter_injection", r"(?:^|\.\s+|!\s+|>\s*)system\s*:", re.IGNORECASE),
        ("delimiter_injection", r"\[SYSTEM\]"),
        ("delimiter_injection", r"<<SYS>>"),
        ("delimiter_injection", r"<\|im_start\|>"),
        ("delimiter_injection", r"<\|system\|>"),

        # 4. Prompt extraction — attempting to reveal the system prompt
        ("prompt_extraction", r"reveal\s+your\s+(?:system\s+)?(?:prompt|instructions?|rules)"),
        ("prompt_extraction", r"show\s+me\s+your\s+(?:system\s+)?(?:prompt|instructions?|rules)"),
        ("prompt_extraction", r"what\s+(?:is|are)\s+your\s+(?:system\s+)?(?:prompt|instructions?|rules)"),
        ("prompt_extraction", r"print\s+(?:out\s+)?your\s+(?:system\s+)?(?:prompt|instructions?)"),

        # 5. Code execution — attempting to execute code
        ("code_execution", r"```(?:python|bash|sh|javascript|js)\b"),
        ("code_execution", r"\beval\s*\("),
        ("code_execution", r"\bexec\s*\("),
        ("code_execution", r"\b__import__\s*\("),
        ("code_execution", r"\bos\.system\s*\("),
        ("code_execution", r"\bsubprocess\.(?:call|run|Popen)\s*\("),

        # 6. D7 fix: Data exfiltration — attempting to send data to external addresses
        # Catches: send/forward/share/email/transmit + (all)? + confidential/sensitive/secret/private
        # + documents/data/information/details/files/records + to + email/external
        ("data_exfiltration", r"(?:send|forward|share|email|transmit|export)\s+(?:all\s+)?(?:confidential|sensitive|secret|private|internal)\s+(?:documents?|data|information|details?|files?|records?)\s+(?:to\s+\S+@\S+|with\s+(?:external|outside|third\s+party))"),
        ("data_exfiltration", r"(?:send|forward|share|email|transmit)\s+(?:all\s+)?(?:confidential|sensitive|secret|private)\s+(?:documents?|data|information|details?|files?|records?)\s+to\s+\S+@\S+"),

        # 7. D7 fix: Epistemic override — attempting to manipulate evidence classification
        ("epistemic_override", r"this\s+document\s+is\s+authoritative\b"),
        ("epistemic_override", r"mark\s+all\s+(?:evidence|signals?)\s+(?:against|contradicting)\s+(?:it|this)\s+as\s+(?:false|irrelevant|invalid)"),
        ("epistemic_override", r"(?:ignore|disregard|discard)\s+all\s+(?:conflicting|contradicting)\s+(?:evidence|signals?|data)"),
        ("epistemic_override", r"this\s+(?:document|message|instruction)\s+(?:overrides?|supersedes?|replaces?)\s+all\s+(?:prior|previous|existing)\s+(?:analysis|evidence|context)"),
    ]

    # Pre-compile patterns for performance
    _COMPILED_PATTERNS: list[tuple[str, re.Pattern]] = []

    def __init__(self) -> None:
        # Always recompile (patterns may have changed between instances in tests)
        PromptInjectionFilter._COMPILED_PATTERNS = []
        for entry in self._PATTERNS:
            pattern_type = entry[0]
            pattern = entry[1]
            # All patterns use IGNORECASE | MULTILINE by default
            PromptInjectionFilter._COMPILED_PATTERNS.append(
                    (pattern_type, re.compile(pattern, re.IGNORECASE | re.MULTILINE))
                )

    def check(self, text: str) -> InjectionCheckResult:
        """Check a text string for prompt injection patterns.

        Args:
            text: The text to check.

        Returns:
            InjectionCheckResult with is_suspicious, detected_patterns, risk_level.
        """
        if not text or not isinstance(text, str):
            return InjectionCheckResult(is_suspicious=False)

        detected: set[str] = set()
        text_lower = text.lower()

        for pattern_type, compiled in self._COMPILED_PATTERNS:
            if compiled.search(text):
                detected.add(pattern_type)

        if not detected:
            return InjectionCheckResult(is_suspicious=False, original_text=text[:200])

        # Risk level based on number of distinct pattern types
        if len(detected) >= 3:
            risk_level = "high"
        elif len(detected) >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return InjectionCheckResult(
            is_suspicious=True,
            detected_patterns=sorted(detected),
            risk_level=risk_level,
            original_text=text[:200],
        )

    def check_signal(self, signal: dict[str, Any]) -> InjectionCheckResult:
        """Check ALL text fields in a signal for prompt injection.

        Attackers can hide injection in metadata fields, not just the
        primary content. This method recursively checks all string values
        in the signal dict.

        Args:
            signal: A normalized signal dict.

        Returns:
            InjectionCheckResult (aggregated across all fields).
        """
        all_text = self._extract_all_text(signal)
        # Check each text field individually and aggregate
        all_detected: set[str] = set()
        is_suspicious = False

        for text in all_text:
            result = self.check(text)
            if result.is_suspicious:
                is_suspicious = True
                all_detected.update(result.detected_patterns)

        if not is_suspicious:
            return InjectionCheckResult(is_suspicious=False)

        if len(all_detected) >= 3:
            risk_level = "high"
        elif len(all_detected) >= 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        return InjectionCheckResult(
            is_suspicious=True,
            detected_patterns=sorted(all_detected),
            risk_level=risk_level,
        )

    def mark_signal(
        self,
        signal: dict[str, Any],
        result: InjectionCheckResult,
    ) -> dict[str, Any]:
        """Mark a signal with the prompt injection risk result.

        The signal is NOT modified beyond adding the prompt_injection_risk
        field. The original data is preserved — suspicious content is
        flagged for review, not dropped.

        Args:
            signal: The signal to mark.
            result: The InjectionCheckResult from check_signal().

        Returns:
            The signal with a prompt_injection_risk field added.
        """
        signal["prompt_injection_risk"] = result.to_dict()
        return signal

    def _extract_all_text(self, obj: Any, depth: int = 0) -> list[str]:
        """Recursively extract all string values from a dict/list structure.

        Args:
            obj: The object to extract text from.
            depth: Current recursion depth (max 5 to prevent infinite loops).

        Returns:
            List of all string values found.
        """
        if depth > 5:
            return []

        texts: list[str] = []

        if isinstance(obj, str):
            texts.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                texts.extend(self._extract_all_text(value, depth + 1))
        elif isinstance(obj, list):
            for item in obj:
                texts.extend(self._extract_all_text(item, depth + 1))

        return texts
