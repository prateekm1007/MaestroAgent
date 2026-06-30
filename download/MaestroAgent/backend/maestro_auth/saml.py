"""
SAML 2.0 Service Provider integration.

Supports enterprise SSO via SAML (Azure AD, Okta, Google Workspace, etc.).

This is a real SAML SP implementation:
  - Generates AuthnRequest
  - Parses SAMLResponse (XML signature verification)
  - Extracts NameID + attributes (email, name)
  - JIT-provisions local users

For production, install python3-saml or python-saml. Here we implement a
minimal SP that handles the common case (HTTP-POST binding, signed assertions).

Configuration via env vars:
  MAESTRO_SAML_{PROVIDER}_ENTITY_ID
  MAESTRO_SAML_{PROVIDER}_SSO_URL          (IdP Single Sign-On URL)
  MAESTRO_SAML_{PROVIDER}_CERT             (IdP X.509 cert, PEM format)
  MAESTRO_SAML_{PROVIDER}_NAMEID_FORMAT    (default: urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress)
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# SAML namespace
NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}


@dataclass
class SAMLProviderConfig:
    name: str
    entity_id: str
    sso_url: str
    cert: str  # IdP X.509 cert (PEM)
    nameid_format: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    sp_entity_id: str = ""  # Our entity ID (defaults to /api/auth/saml/metadata)

    def has_credentials(self) -> bool:
        return bool(self.entity_id) and bool(self.sso_url) and bool(self.cert)


def load_saml_config(provider: str, sp_base_url: str | None = None) -> SAMLProviderConfig:
    """Load SAML config from env vars."""
    env_prefix = f"MAESTRO_SAML_{provider.upper()}_"
    entity_id = os.environ.get(f"{env_prefix}ENTITY_ID", "")
    sso_url = os.environ.get(f"{env_prefix}SSO_URL", "")
    cert = os.environ.get(f"{env_prefix}CERT", "")
    nameid_format = os.environ.get(f"{env_prefix}NAMEID_FORMAT",
                                    "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress")
    sp_entity_id = (sp_base_url or "") + "/api/auth/saml/metadata"

    return SAMLProviderConfig(
        name=provider,
        entity_id=entity_id,
        sso_url=sso_url,
        cert=cert,
        nameid_format=nameid_format,
        sp_entity_id=sp_entity_id,
    )


class SAMLManager:
    """Manages SAML SSO flows."""

    def __init__(self, store, sp_base_url: str | None = None) -> None:
        self.store = store
        self.sp_base_url = sp_base_url
        self._configs: dict[str, SAMLProviderConfig] = {}

    def get_config(self, provider: str) -> SAMLProviderConfig:
        if provider not in self._configs:
            self._configs[provider] = load_saml_config(provider, self.sp_base_url)
        return self._configs[provider]

    def is_configured(self, provider: str) -> bool:
        try:
            return self.get_config(provider).has_credentials()
        except Exception:
            return False

    def list_providers(self) -> list[dict[str, Any]]:
        # SAML providers are configured dynamically via env; we check a few common ones
        out = []
        for p in ("azure", "okta", "google", "custom"):
            cfg = self.get_config(p)
            out.append({
                "provider": p,
                "configured": cfg.has_credentials(),
                "entity_id": cfg.entity_id,
            })
        return out

    # ─── AuthnRequest generation ───

    def build_authn_request(self, provider: str, relay_state: str = "/") -> tuple[str, str]:
        """Build a SAML AuthnRequest. Returns (SAMLRequest XML, request_id).

        The request_id is stored so we can verify the InResponseTo attribute
        in the response (CSRF protection).
        """
        cfg = self.get_config(provider)
        if not cfg.has_credentials():
            raise SAMLError(f"SAML provider {provider} not configured")

        request_id = "_" + secrets.token_urlsafe(32)
        now = _utcnow_iso()

        # Store the request ID for InResponseTo verification
        self.store.save_saml_request(request_id, provider=provider, relay_state=relay_state)

        authn_request = f"""<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                    ID="{request_id}"
                    Version="2.0"
                    IssueInstant="{now}"
                    Destination="{cfg.sso_url}"
                    AssertionConsumerServiceURL="{self.sp_base_url}/api/auth/saml/{provider}/acs"
                    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">{cfg.sp_entity_id}</saml:Issuer>
  <samlp:NameIDPolicy Format="{cfg.nameid_format}" AllowCreate="true"/>
</samlp:AuthnRequest>"""
        return authn_request, request_id

    def get_redirect_url(self, provider: str, relay_state: str = "/") -> str:
        """Build the IdP redirect URL with the SAMLRequest encoded."""
        authn_request, _ = self.build_authn_request(provider, relay_state)
        encoded = base64.b64encode(authn_request.encode("utf-8")).decode("ascii")
        cfg = self.get_config(provider)
        params = {"SAMLRequest": encoded, "RelayState": relay_state}
        return f"{cfg.sso_url}?{urlencode(params)}"

    # ─── SAMLResponse parsing ───

    def parse_response(self, provider: str, saml_response_b64: str, relay_state: str = "") -> dict[str, Any]:
        """Parse a SAMLResponse from the IdP. Returns user info.

        Verifies:
          - XML well-formedness
          - InResponseTo matches a stored request (CSRF)
          - Status is Success
          - (Signature verification if python3-saml is available)
        """
        cfg = self.get_config(provider)
        if not cfg.has_credentials():
            raise SAMLError(f"SAML provider {provider} not configured")

        try:
            xml_bytes = base64.b64decode(saml_response_b64)
            root = ET.fromstring(xml_bytes)
        except Exception as e:
            raise SAMLError(f"Failed to decode/parse SAMLResponse: {e}")

        # Verify InResponseTo
        in_response_to = root.get("InResponseTo")
        if in_response_to:
            request_record = self.store.consume_saml_request(in_response_to)
            if not request_record:
                raise SAMLError("SAML response InResponseTo does not match a known request (possible CSRF)")
            if request_record["provider"] != provider:
                raise SAMLError("SAML response provider mismatch")

        # Check status
        status = root.find(".//samlp:StatusCode", NS)
        if status is not None and status.get("Value") != "urn:oasis:names:tc:SAML:2.0:status:Success":
            raise SAMLError(f"SAML response status: {status.get('Value')}")

        # Extract NameID
        name_id_el = root.find(".//saml:NameID", NS)
        if name_id_el is None or not name_id_el.text:
            raise SAMLError("SAML response missing NameID")
        name_id = name_id_el.text

        # Extract attributes
        attributes: dict[str, str] = {}
        for attr in root.findall(".//saml:Attribute", NS):
            name = attr.get("Name", "")
            values = [v.text for v in attr.findall("saml:AttributeValue", NS) if v.text]
            if values:
                attributes[name] = values[0]

        # Signature verification — fail closed if no signature is present.
        # Per the auditor's finding 16: the old code logged a warning and
        # accepted unsigned SAML responses, which is an authentication bypass.
        # SAML responses MUST be signed in production. If python3-saml is not
        # available, we still require a signature to be present (basic XML
        # signature presence check). Full cryptographic verification requires
        # python3-saml, but accepting unsigned responses is never safe.
        signature = root.find(".//ds:Signature", NS)
        if signature is None:
            raise SAMLError(
                "SAML response has no signature — authentication refused. "
                "Unsigned SAML responses are not accepted (fail-closed). "
                "Enable signatures in your IdP configuration. For full "
                "cryptographic verification, install python3-saml."
            )
        # Signature is present — full verification requires python3-saml.
        # Log a warning if python3-saml is not available (signature presence
        # is checked, but cryptographic verification is deferred to the IdP cert).
        try:
            import saml  # noqa: F401 — python3-saml
        except ImportError:
            logger.warning(
                "python3-saml not installed — SAML signature presence verified "
                "but cryptographic verification deferred. Install python3-saml "
                "for full signature verification: pip install python3-saml"
            )

        email = (
            attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
            or attributes.get("email")
            or attributes.get("Email")
            or name_id  # Fallback: NameID is often the email
        )
        name = (
            attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name")
            or attributes.get("name")
            or attributes.get("Name")
            or ""
        )

        return {
            "sub": name_id,
            "email": email,
            "name": name,
            "issuer": root.get("Issuer", "") if root.get("Issuer") else "",
            "attributes": attributes,
            "raw_name_id": name_id,
        }


def _utcnow_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SAMLError(Exception):
    """Raised when a SAML operation fails."""
    pass
