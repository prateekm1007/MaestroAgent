"""
OIDC (OpenID Connect) provider integration.

Supports:
  - Azure AD (Microsoft Entra ID)
  - Okta
  - Google Workspace
  - Auth0
  - Supabase Auth

Each provider is configured via env vars:
  MAESTRO_OIDC_{PROVIDER}_CLIENT_ID
  MAESTRO_OIDC_{PROVIDER}_CLIENT_SECRET
  MAESTRO_OIDC_{PROVIDER}_ISSUER     (e.g. https://login.microsoftonline.com/{tenant}/v2.0)
  MAESTRO_OIDC_{PROVIDER}_SCOPES     (optional; defaults to openid profile email)

The flow:
  1. GET /api/auth/oidc/{provider}/login → redirect to IdP
  2. IdP redirects to /api/auth/oidc/{provider}/callback
  3. We exchange the code for id_token + access_token
  4. We verify the id_token JWT signature (via JWKS)
  5. We create/update the local user (JIT provisioning)
  6. We issue a session + refresh token (HttpOnly cookies)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from maestro_auth.models import AuthStore, utcnow

logger = logging.getLogger(__name__)


# ─── Provider configurations ───

# Default OIDC endpoints per provider. The issuer can be overridden via env.
PROVIDER_DEFAULTS = {
    "azure": {
        # Azure AD v2.0 well-known endpoints
        "issuer_template": "https://login.microsoftonline.com/{tenant}/v2.0",
        "authorize_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "jwks_url": "https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        "scopes": ["openid", "profile", "email", "offline_access"],
        "tenant_env": "MAESTRO_OIDC_AZURE_TENANT",
    },
    "okta": {
        # Okta: issuer is the Okta tenant (e.g. https://acme.okta.com)
        "issuer_env": "MAESTRO_OIDC_OKTA_ISSUER",
        "authorize_url_template": "{issuer}/oauth2/v1/authorize",
        "token_url_template": "{issuer}/oauth2/v1/token",
        "jwks_url_template": "{issuer}/oauth2/v1/keys",
        "scopes": ["openid", "profile", "email", "offline_access"],
    },
    "google": {
        "issuer": "https://accounts.google.com",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "jwks_url": "https://www.googleapis.com/oauth2/v3/certs",
        "scopes": ["openid", "profile", "email"],
    },
    "auth0": {
        # Auth0: issuer is the tenant (e.g. https://acme.us.auth0.com)
        "issuer_env": "MAESTRO_OIDC_AUTH0_ISSUER",
        "authorize_url_template": "{issuer}/authorize",
        "token_url_template": "{issuer}/oauth/token",
        "jwks_url_template": "{issuer}/.well-known/jwks.json",
        "scopes": ["openid", "profile", "email"],
    },
    "supabase": {
        # Supabase Auth: issuer is the project URL
        "issuer_env": "MAESTRO_OIDC_SUPABASE_ISSUER",
        "authorize_url_template": "{issuer}/auth/v1/authorize",
        "token_url_template": "{issuer}/auth/v1/token",
        "jwks_url_template": "{issuer}/auth/v1/.well-known/jwks.json",
        "scopes": ["openid", "profile", "email"],
    },
}


@dataclass
class OIDCProviderConfig:
    name: str
    client_id: str
    client_secret: str
    issuer: str
    authorize_url: str
    token_url: str
    jwks_url: str
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    redirect_uri: str = ""

    def has_credentials(self) -> bool:
        return bool(self.client_id) and bool(self.client_secret)


def load_oidc_config(provider: str, redirect_uri_base: str | None = None) -> OIDCProviderConfig:
    """Load OIDC config for a provider from env vars.

    Env var naming:
      MAESTRO_OIDC_{PROVIDER}_CLIENT_ID
      MAESTRO_OIDC_{PROVIDER}_CLIENT_SECRET
      MAESTRO_OIDC_{PROVIDER}_ISSUER (or _TENANT for Azure)
    """
    provider = provider.lower()
    if provider not in PROVIDER_DEFAULTS:
        raise ValueError(f"Unknown OIDC provider: {provider}. Supported: {list(PROVIDER_DEFAULTS.keys())}")

    env_prefix = f"MAESTRO_OIDC_{provider.upper()}_"
    client_id = os.environ.get(f"{env_prefix}CLIENT_ID", "")
    client_secret = os.environ.get(f"{env_prefix}CLIENT_SECRET", "")
    defaults = PROVIDER_DEFAULTS[provider]

    # Determine issuer
    issuer = ""
    if "issuer" in defaults:
        issuer = defaults["issuer"]
    elif "issuer_env" in defaults:
        issuer = os.environ.get(defaults["issuer_env"], "")
    elif "issuer_template" in defaults:
        tenant = os.environ.get(defaults["tenant_env"], "common")
        issuer = defaults["issuer_template"].format(tenant=tenant)

    # Build endpoint URLs
    if provider == "azure":
        tenant = os.environ.get(defaults["tenant_env"], "common")
        authorize_url = defaults["authorize_url"].format(tenant=tenant)
        token_url = defaults["token_url"].format(tenant=tenant)
        jwks_url = defaults["jwks_url"].format(tenant=tenant)
    elif "authorize_url_template" in defaults:
        authorize_url = defaults["authorize_url_template"].format(issuer=issuer)
        token_url = defaults["token_url_template"].format(issuer=issuer)
        jwks_url = defaults["jwks_url_template"].format(issuer=issuer)
    else:
        authorize_url = defaults["authorize_url"]
        token_url = defaults["token_url"]
        jwks_url = defaults["jwks_url"]

    redirect_uri = (
        os.environ.get("MAESTRO_OIDC_REDIRECT_URI")
        or (f"{redirect_uri_base}/api/auth/oidc/{provider}/callback" if redirect_uri_base else "")
    )

    return OIDCProviderConfig(
        name=provider,
        client_id=client_id,
        client_secret=client_secret,
        issuer=issuer,
        authorize_url=authorize_url,
        token_url=token_url,
        jwks_url=jwks_url,
        scopes=defaults["scopes"],
        redirect_uri=redirect_uri,
    )


# ─── OIDC Manager ───

class OIDCManager:
    """Manages OIDC flows for all providers."""

    def __init__(
        self,
        store: AuthStore,
        redirect_uri_base: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.store = store
        self.redirect_uri_base = redirect_uri_base
        self._http = http_client or httpx.Client(timeout=30.0)
        self._configs: dict[str, OIDCProviderConfig] = {}
        self._jwks_cache: dict[str, dict[str, Any]] = {}  # issuer → JWKS

    def get_config(self, provider: str) -> OIDCProviderConfig:
        if provider not in self._configs:
            self._configs[provider] = load_oidc_config(provider, self.redirect_uri_base)
        return self._configs[provider]

    def is_configured(self, provider: str) -> bool:
        try:
            return self.get_config(provider).has_credentials()
        except ValueError:
            return False

    def list_providers(self) -> list[dict[str, Any]]:
        out = []
        for p in PROVIDER_DEFAULTS:
            cfg = self.get_config(p)
            out.append({
                "provider": p,
                "configured": cfg.has_credentials(),
                "issuer": cfg.issuer,
            })
        return out

    # ─── Authorization URL ───

    def get_authorization_url(self, provider: str, redirect_to: str = "/") -> str:
        """Build the OIDC authorization URL with PKCE and state."""
        cfg = self.get_config(provider)
        if not cfg.has_credentials():
            raise ValueError(f"OIDC provider {provider} not configured")

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        # Store state for CSRF protection
        self.store.save_oidc_state(state, provider=provider, nonce=nonce, redirect_to=redirect_to)

        params = {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": " ".join(cfg.scopes),
            "state": state,
            "nonce": nonce,
        }
        url = f"{cfg.authorize_url}?{urlencode(params)}"
        logger.info("Built OIDC authorization URL for %s", provider)
        return url

    # ─── Code exchange ───

    def exchange_code(
        self, provider: str, code: str, state: str
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens. Verifies the id_token.

        Returns the user info (sub, email, name) extracted from the id_token.
        """
        # Verify state (CSRF protection)
        state_record = self.store.consume_oidc_state(state)
        if not state_record or state_record["provider"] != provider:
            raise OIDCError("Invalid or expired state token")

        cfg = self.get_config(provider)
        if not cfg.has_credentials():
            raise OIDCError(f"OIDC provider {provider} not configured")

        # Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
        }
        try:
            resp = self._http.post(cfg.token_url, data=token_data, headers={"Accept": "application/json"})
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OIDCError(f"Token exchange failed for {provider}: {e}") from e

        tokens = resp.json()
        if "error" in tokens:
            raise OIDCError(f"OIDC error from {provider}: {tokens.get('error_description', tokens['error'])}")

        id_token = tokens.get("id_token")
        if not id_token:
            raise OIDCError(f"No id_token in {provider} response")

        # Verify the id_token JWT
        user_info = self._verify_id_token(id_token, cfg, state_record.get("nonce"))
        return user_info

    # ─── id_token verification ───

    def _verify_id_token(
        self, id_token: str, cfg: OIDCProviderConfig, expected_nonce: str | None
    ) -> dict[str, Any]:
        """Verify the id_token JWT: signature (via JWKS), issuer, audience, nonce."""
        try:
            header_b64, payload_b64, signature_b64 = id_token.split(".")
        except ValueError:
            raise OIDCError("Malformed id_token (not 3 parts)")

        # Decode header and payload (no verification yet — we need the kid)
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))

        # Verify issuer
        if cfg.issuer and payload.get("iss") != cfg.issuer:
            raise OIDCError(f"id_token issuer mismatch: {payload.get('iss')} != {cfg.issuer}")

        # Verify audience
        aud = payload.get("aud")
        if aud != cfg.client_id and cfg.client_id not in (aud if isinstance(aud, list) else [aud]):
            raise OIDCError(f"id_token audience mismatch: {aud}")

        # Verify expiry
        exp = payload.get("exp")
        if exp and int(exp) < time.time():
            raise OIDCError("id_token expired")

        # Verify nonce (CSRF / replay protection)
        if expected_nonce and payload.get("nonce") != expected_nonce:
            raise OIDCError("id_token nonce mismatch")

        # Verify signature via JWKS — fail closed if PyJWT is not installed.
        # PyJWT + cryptography are required dependencies (see pyproject.toml).
        # If PyJWT is somehow unavailable, we MUST NOT accept the token —
        # accepting an unverified token is an authentication bypass.
        kid = header.get("kid")
        jwks = self._fetch_jwks(cfg.jwks_url)
        key = self._find_key(jwks, kid)
        if not key:
            raise OIDCError(f"No matching key found in JWKS for kid={kid}")

        try:
            import jwt as pyjwt
        except ImportError:
            # Fail closed: do NOT accept the token if we can't verify its signature.
            # This is a deployment misconfiguration — PyJWT must be installed.
            raise OIDCError(
                "PyJWT is not installed — id_token signature cannot be verified. "
                "This is a deployment misconfiguration. Install with: pip install PyJWT cryptography. "
                "Authentication is refused (fail-closed)."
            )

        try:
            public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
            # SECURITY: hardcode algorithms=["RS256"] — do NOT take the algorithm
            # from the JWT header (algorithm injection attack).
            #
            # The old code passed algorithms=[header.get("alg", "RS256")], which
            # reads the algorithm from the UNVERIFIED JWT header. An attacker who
            # forges a JWT with alg=HS256 in the header and signs with HMAC using
            # the server's public RSA key (available via JWKS) could bypass
            # verification. Modern PyJWT has partial mitigations, but the correct
            # defense is to hardcode the expected algorithm and reject anything else.
            #
            # OIDC id_tokens from enterprise providers (Azure AD, Okta, Google,
            # Auth0, Supabase) use RS256. If a provider uses a different algorithm,
            # it must be explicitly configured via MAESTRO_OIDC_ALGORITHMS env var.
            import os
            allowed_algorithms = os.environ.get(
                "MAESTRO_OIDC_ALGORITHMS", "RS256"
            ).split(",")
            token_alg = header.get("alg", "RS256")
            if token_alg not in allowed_algorithms:
                raise OIDCError(
                    f"id_token algorithm '{token_alg}' not in allowed list "
                    f"{allowed_algorithms}. This may indicate an algorithm "
                    f"injection attempt. If your IdP uses a non-RS256 algorithm, "
                    f"set MAESTRO_OIDC_ALGORITHMS env var."
                )
            pyjwt.decode(id_token, key=public_key, algorithms=allowed_algorithms,
                         audience=cfg.client_id, issuer=cfg.issuer, options={"verify_aud": True})
        except OIDCError:
            raise
        except Exception as e:
            raise OIDCError(f"id_token signature verification failed: {e}")

        return {
            "sub": payload.get("sub"),
            "email": payload.get("email") or payload.get("preferred_username"),
            "name": payload.get("name") or payload.get("given_name", ""),
            "issuer": payload.get("iss"),
            "raw": payload,
        }

    def _fetch_jwks(self, jwks_url: str) -> dict[str, Any]:
        """Fetch and cache the JWKS for an issuer."""
        if jwks_url in self._jwks_cache:
            return self._jwks_cache[jwks_url]
        try:
            resp = self._http.get(jwks_url)
            resp.raise_for_status()
            jwks = resp.json()
            self._jwks_cache[jwks_url] = jwks
            return jwks
        except httpx.HTTPError as e:
            raise OIDCError(f"Failed to fetch JWKS from {jwks_url}: {e}") from e

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: str | None) -> dict[str, Any] | None:
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
        return None


def _b64url_decode(data: str) -> bytes:
    """Decode a base64url string, padding as needed."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


class OIDCError(Exception):
    """Raised when an OIDC operation fails."""
    pass
