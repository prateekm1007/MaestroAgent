
"""SSO/SAML/OIDC configuration and stub handlers for enterprise SSO."""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SSOConfig:
    """SSO configuration loaded from environment variables."""
    enabled: bool = False
    provider: str = ""  # "saml" or "oidc"
    sso_url: str = ""
    issuer: str = ""
    cert: str = ""
    client_id: str = ""
    client_secret: str = ""

    @classmethod
    def from_env(cls) -> "SSOConfig":
        provider = os.getenv("SSO_PROVIDER", "").lower()  # "saml" or "oidc"
        sso_url = os.getenv("SSO_URL", "")
        issuer = os.getenv("SSO_ISSUER", "")
        cert = os.getenv("SSO_CERT", "")
        client_id = os.getenv("SSO_CLIENT_ID", "")
        client_secret = os.getenv("SSO_CLIENT_SECRET", "")

        enabled = bool(provider and sso_url and issuer)

        if enabled:
            logger.info(f"SSO enabled: provider={provider}, issuer={issuer}")
        else:
            logger.info("SSO not configured — endpoints will return 501")

        return cls(
            enabled=enabled,
            provider=provider,
            sso_url=sso_url,
            issuer=issuer,
            cert=cert,
            client_id=client_id,
            client_secret=client_secret,
        )


# Global config instance
_sso_config: Optional[SSOConfig] = None


def get_sso_config() -> SSOConfig:
    global _sso_config
    if _sso_config is None:
        _sso_config = SSOConfig.from_env()
    return _sso_config


def validate_saml_assertion(saml_response: str) -> dict:
    """
    Stub: validate a SAML assertion and return user attributes.
    Returns a dict with keys: email, name, groups.
    Raises NotImplementedError if SSO is not configured.
    """
    config = get_sso_config()
    if not config.enabled or config.provider != "saml":
        raise NotImplementedError("SAML SSO is not configured")

    # In production, this would:
    # 1. Parse the SAML response
    # 2. Verify the signature using config.cert
    # 3. Check the issuer matches config.issuer
    # 4. Extract user attributes
    logger.warning("SAML validation is a stub — returning mock user for development")
    return {
        "email": "sso-user@example.com",
        "name": "SSO User",
        "groups": ["users"],
    }


def validate_oidc_token(id_token: str) -> dict:
    """
    Stub: validate an OIDC token and return user attributes.
    Returns a dict with keys: email, name, groups.
    Raises NotImplementedError if SSO is not configured.
    """
    config = get_sso_config()
    if not config.enabled or config.provider != "oidc":
        raise NotImplementedError("OIDC SSO is not configured")

    # In production, this would:
    # 1. Decode and verify the JWT
    # 2. Validate issuer, audience, expiry
    # 3. Extract claims
    logger.warning("OIDC validation is a stub — returning mock user for development")
    return {
        "email": "sso-user@example.com",
        "name": "SSO User",
        "groups": ["users"],
    }

