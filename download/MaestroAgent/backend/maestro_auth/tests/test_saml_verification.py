"""
Round 53 C1 — SAML signature verification tests.

Tests that the SAML fail-closed logic works correctly:
  1. Missing signature → rejected
  2. Missing IdP cert → rejected
  3. Valid signature structure (mocked) → accepted
  4. Dependencies declared in pyproject.toml
"""
from __future__ import annotations

import base64
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _clear_saml_env():
    """Clear SAML env vars before each test."""
    old = os.environ.pop("MAESTRO_SAML_IDP_CERT", None)
    yield
    if old is not None:
        os.environ["MAESTRO_SAML_IDP_CERT"] = old


def _make_manager():
    """Create a SAMLManager with a mock store that returns a configured provider."""
    from maestro_auth.saml import SAMLManager, SAMLProviderConfig
    mock_store = MagicMock()
    manager = SAMLManager(store=mock_store, sp_base_url="https://maestro.local")
    # Mock get_config to return a configured provider
    cfg = SAMLProviderConfig(
        name="test-provider",
        entity_id="https://idp.example.com",
        sso_url="https://idp.example.com/sso",
        cert="-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----",
    )
    manager.get_config = MagicMock(return_value=cfg)
    return manager


class TestSAMLFailClosed:
    """SAML must fail closed on any misconfiguration."""

    def test_missing_signature_rejected(self):
        """A SAML response with no signature must be rejected."""
        from maestro_auth.saml import SAMLError
        manager = _make_manager()

        unsigned_xml = (
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
            ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">'
            '<saml:Assertion><saml:Subject><saml:NameID>user@example.com</saml:NameID>'
            '</saml:Subject></saml:Assertion></samlp:Response>'
        )
        encoded = base64.b64encode(unsigned_xml.encode()).decode()

        with pytest.raises(SAMLError, match="no signature"):
            manager.parse_response("test-provider", encoded)

    def test_missing_idp_cert_rejected(self):
        """A SAML response with a signature but no IdP cert must be rejected."""
        from maestro_auth.saml import SAMLError
        manager = _make_manager()

        signed_xml = (
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
            ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
            ' xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
            '<saml:Assertion><saml:Subject><saml:NameID>user@example.com</saml:NameID>'
            '</saml:Subject></saml:Assertion>'
            '<ds:Signature><ds:SignatureValue>fake</ds:SignatureValue></ds:Signature>'
            '</samlp:Response>'
        )
        encoded = base64.b64encode(signed_xml.encode()).decode()

        # No MAESTRO_SAML_IDP_CERT set — must fail closed (either no cert or no python3-saml)
        with pytest.raises(SAMLError, match="MAESTRO_SAML_IDP_CERT|python3-saml|fail-closed"):
            manager.parse_response("test-provider", encoded)

    def test_valid_signature_accepted_with_mock(self):
        """When xmlsec verifies successfully, the response is accepted."""
        from maestro_auth.saml import SAMLManager, SAMLProviderConfig
        os.environ["MAESTRO_SAML_IDP_CERT"] = "-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----"
        manager = _make_manager()

        signed_xml = (
            '<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"'
            ' xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"'
            ' xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
            '<saml:Issuer>https://idp.example.com</saml:Issuer>'
            '<saml:Assertion><saml:Subject><saml:NameID>user@example.com</saml:NameID>'
            '</saml:Subject>'
            '<saml:AttributeStatement><saml:Attribute Name="email">'
            '<saml:AttributeValue>user@example.com</saml:AttributeValue>'
            '</saml:Attribute></saml:AttributeStatement>'
            '</saml:Assertion>'
            '<ds:Signature><ds:SignatureValue>fake</ds:SignatureValue></ds:Signature>'
            '</samlp:Response>'
        )
        encoded = base64.b64encode(signed_xml.encode()).decode()

        mock_ctx = MagicMock()
        mock_ctx.verify = MagicMock(return_value=True)
        with patch.dict('sys.modules', {
            'saml': MagicMock(),  # Mock python3-saml
            'xmlsec': MagicMock(SignatureContext=MagicMock(return_value=mock_ctx),
                               Key=MagicMock(from_memory=MagicMock(return_value=MagicMock()))),
            'lxml': MagicMock(etree=MagicMock(fromstring=MagicMock())),
        }):
            result = manager.parse_response("test-provider", encoded)

        assert result is not None
        assert result["email"] == "user@example.com"

    def test_dependencies_declared_in_pyproject(self):
        """python3-saml, xmlsec, and lxml must be in pyproject.toml."""
        import pathlib
        pyproject = pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml"
        content = pyproject.read_text()
        assert "python3-saml" in content, "python3-saml not in pyproject.toml"
        assert "xmlsec" in content, "xmlsec not in pyproject.toml"
        assert "lxml" in content, "lxml not in pyproject.toml"
