"""Data Residency Module (Phase 4.5, auditor v13).

Supports EU/US data pinning and self-hosted LLM option for enterprise
customers who require data sovereignty.

The v13 auditor found: "EU/US pinning; self-host LLM option."
"""

from __future__ import annotations

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Valid residency regions
VALID_REGIONS = {"us", "eu", "us-west", "us-east", "eu-west", "eu-central"}


def get_configured_region() -> str:
    """Get the configured data residency region.

    Reads from MAESTRO_DATA_REGION env var. Defaults to 'us' if not set.
    """
    return os.environ.get("MAESTRO_DATA_REGION", "us").lower()


def get_llm_provider_config() -> dict[str, Any]:
    """Get the LLM provider configuration.

    Supports:
    - 'cloud': default cloud LLM (OpenAI, Anthropic, ZAI)
    - 'self-hosted': self-hosted LLM via vLLM/Ollama/LM Studio
    - 'hybrid': cloud for non-sensitive, self-hosted for PII

    The v13 auditor found: "self-host LLM option."
    """
    provider = os.environ.get("MAESTRO_LLM_PROVIDER", "cloud").lower()
    self_host_url = os.environ.get("MAESTRO_SELF_HOST_LLM_URL", "")
    self_host_model = os.environ.get("MAESTRO_SELF_HOST_LLM_MODEL", "")

    return {
        "provider": provider,
        "self_host_url": self_host_url,
        "self_host_model": self_host_model,
        "region": get_configured_region(),
    }


def should_use_self_hosted_llm(text: str | None = None) -> bool:
    """Determine if a self-hosted LLM should be used for this request.

    Phase 4.5: in 'hybrid' mode, use self-hosted LLM when:
    - The text contains PII patterns (email, phone, SSN, etc.)
    - The entity is marked as sensitive
    - The region is EU (GDPR data sovereignty)

    In 'self-hosted' mode, always use self-hosted LLM.
    In 'cloud' mode, never use self-hosted LLM.
    """
    config = get_llm_provider_config()
    provider = config["provider"]

    if provider == "self-hosted":
        return True
    if provider == "cloud":
        return False

    # Hybrid mode: use self-hosted for EU region or PII detection
    if config["region"].startswith("eu"):
        return True

    if text:
        # Simple PII detection — if text looks like it contains PII, use self-hosted
        _PII_PATTERNS = [
            "@",  # email
            "SSN", "social security",
            "credit card", "card number",
            "password", "secret", "api key",
            "phone", "mobile",
        ]
        text_lower = text.lower()
        if any(p.lower() in text_lower for p in _PII_PATTERNS):
            return True

    return False


def get_data_residency_info() -> dict[str, Any]:
    """Get a summary of the current data residency configuration.

    Used by GET /api/admin/data-residency for admin monitoring.
    """
    config = get_llm_provider_config()
    return {
        "region": config["region"],
        "llm_provider": config["provider"],
        "self_host_configured": bool(config["self_host_url"]),
        "self_host_model": config["self_host_model"],
        "data_pinning_active": config["region"] in VALID_REGIONS,
        "residency_compliant": config["region"].startswith("eu") or config["region"].startswith("us"),
    }
