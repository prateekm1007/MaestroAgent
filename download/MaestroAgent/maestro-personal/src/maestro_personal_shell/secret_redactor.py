"""Secret/OTP redaction utility — shared between ingestion and Ask output."""
import re
from typing import Any

# Context keywords that indicate a following digit sequence is an OTP/code
_OTP_CONTEXT = (
    r'(?:otp|one[\s-]?time[\s-]?password|verification\s+code|verify\s+code'
    r'|auth(?:entication)?\s+code|access\s+code|security\s+code|pin|password'
    r'|passcode|cvv|cvc)'
)

# Known secret keywords — the VALUE after these should be redacted
_SECRET_KEYWORDS = [
    "SECRET_TOKEN", "AUTH_TOKEN", "API_KEY", "PRIVATE_KEY",
    "JWT_SECRET", "ACCESS_TOKEN", "REFRESH_TOKEN", "SESSION_SECRET",
    "PASSWORD", "PASSWD", "PWD",
]

# Common API key value patterns (not keyword-dependent)
_API_KEY_PATTERNS = [
    r'sk-proj-[a-zA-Z0-9_-]{10,}',  # OpenAI project key (MUST be before sk- to avoid partial match)
    r'sk-or-v1-[a-zA-Z0-9]{20,}',    # OpenRouter (MUST be before sk-)
    r'sk-[a-zA-Z0-9]{20,}',          # OpenAI (generic — catches remaining sk- prefixed keys)
    r'ghp_[a-zA-Z0-9]{20,}',         # GitHub PAT
    r'github_pat_[a-zA-Z0-9_]{22,}', # GitHub fine-grained PAT
    r'gsk_[a-zA-Z0-9]{20,}',         # Groq
    r'AKIA[0-9A-Z]{16}',             # AWS access key
    r'xox[bpoa]-[a-zA-Z0-9-]+',      # Slack token
    r'AIza[0-9A-Za-z\-_]{35}',       # Google API key
    r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',  # JWT
]


def redact_secrets(text: str) -> str:
    """Redact OTPs, API keys, and secret values from text.

    Args:
        text: The text to redact (signal text, Ask answer, etc.)

    Returns:
        Text with secrets replaced by [REDACTED_OTP], [REDACTED_KEY], or [REDACTED]
    """
    if not text or not isinstance(text, str):
        return text

    result = text

    # 1. Redact secret keyword + value: "API_KEY=sk-123" → "[REDACTED]"
    # Also catches "password is MySecret123" and "password: xxx"
    for kw in _SECRET_KEYWORDS:
        # Match: keyword + optional separator (:, =, or " is ") + value
        pattern = re.compile(
            re.escape(kw) + r'\s*(?:[:=]\s*|is\s+)\S+',
            re.IGNORECASE,
        )
        result = pattern.sub('[REDACTED]', result)
        # Also redact standalone keyword
        result = result.replace(kw, "[REDACTED]")
        result = result.replace(kw.lower(), "[REDACTED]")

    # 2. Redact OTP codes: "Your OTP is 9907" → "Your OTP is [REDACTED_OTP]"
    result = re.sub(
        _OTP_CONTEXT + r'\s*(?:is|:|=|\s)\s*(\d{4,8})',
        r'[REDACTED_OTP]',
        result,
        flags=re.IGNORECASE,
    )
    # Also catch "9907 is your OTP" (reversed order)
    result = re.sub(
        r'(\d{4,8})\s+is\s+your\s+' + _OTP_CONTEXT,
        r'[REDACTED_OTP]',
        result,
        flags=re.IGNORECASE,
    )

    # 3. Redact known API key value patterns
    for pat in _API_KEY_PATTERNS:
        result = re.sub(pat, '[REDACTED_KEY]', result)

    return result


def redact_secrets_deep(obj: Any) -> Any:
    """Recursively redact secrets from a nested dict/list/str structure.

    Used for AskResponse fields like evidence_refs, counterevidence, etc.
    that may contain signal text with embedded secrets.
    """
    if isinstance(obj, str):
        return redact_secrets(obj)
    elif isinstance(obj, dict):
        return {k: redact_secrets_deep(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [redact_secrets_deep(item) for item in obj]
    return obj
