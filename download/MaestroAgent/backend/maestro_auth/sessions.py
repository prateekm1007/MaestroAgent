"""
Session management with HttpOnly cookies and rotating refresh tokens.

Cookie design:
  - maestro_session: session ID (HttpOnly, Secure, SameSite=Lax)
  - maestro_refresh: refresh token (HttpOnly, Secure, SameSite=Strict)
  - maestro_csrf: CSRF token for double-submit (NOT HttpOnly — readable by JS)

Refresh token rotation:
  - Each refresh produces a new token in the same family
  - If a used token is reused, the entire family is revoked (reuse detection)

Logout:
  - Revokes the session and all refresh tokens
  - Clears the cookies
"""

from __future__ import annotations

import logging
from typing import Any

from maestro_auth.models import AuthStore

logger = logging.getLogger(__name__)


# Cookie names
SESSION_COOKIE = "maestro_session"
REFRESH_COOKIE = "maestro_refresh"
CSRF_COOKIE = "maestro_csrf"

# TTLs
SESSION_TTL_SECONDS = 86400 * 7       # 7 days
REFRESH_TTL_SECONDS = 86400 * 30      # 30 days


class SessionManager:
    """Manages sessions, refresh tokens, and cookies."""

    def __init__(self, store: AuthStore) -> None:
        self.store = store

    # ─── Login ───

    def login(
        self,
        user_id: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Create a session + refresh token for a user.

        Returns a dict with session_id, csrf_token, and refresh_token.
        The caller is responsible for setting the cookies.
        """
        session = self.store.create_session(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            ttl_seconds=SESSION_TTL_SECONDS,
        )
        refresh_token, refresh_record = self.store.create_refresh_token(
            user_id=user_id,
            session_id=session["id"],
            ttl_seconds=REFRESH_TTL_SECONDS,
        )

        # Update last_login
        from maestro_auth.models import utcnow
        self.store.update_user(user_id, last_login_at=utcnow())

        # Audit
        self.store.audit(
            event_type="login",
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            detail={"session_id": session["id"]},
            success=True,
        )

        return {
            "session_id": session["id"],
            "csrf_token": session["csrf_token"],
            "refresh_token": refresh_token,
            "expires_at": session["expires_at"],
        }

    # ─── Logout ───

    def logout(self, session_id: str | None, ip_address: str | None = None) -> None:
        """Revoke a session and all its refresh tokens."""
        if not session_id:
            return
        session = self.store.get_session(session_id)
        user_id = session["user_id"] if session else None
        self.store.revoke_session(session_id)

        self.store.audit(
            event_type="logout",
            user_id=user_id,
            ip_address=ip_address,
            detail={"session_id": session_id},
            success=True,
        )

    # ─── Refresh ───

    def refresh(self, refresh_token: str, ip_address: str | None = None) -> dict[str, Any] | None:
        """Rotate a refresh token. Returns new session info, or None if invalid.

        If the token is reused, the entire family is revoked (reuse detection).
        """
        record = self.store.verify_refresh_token(refresh_token)
        if not record:
            self.store.audit(
                event_type="token_refresh",
                ip_address=ip_address,
                detail={"reason": "invalid_or_reused_token"},
                success=False,
            )
            return None

        # Mark the old token as used
        self.store.mark_token_used(record["id"])

        # Issue a new refresh token in the same family
        new_refresh, new_record = self.store.create_refresh_token(
            user_id=record["user_id"],
            session_id=record["session_id"],
            ttl_seconds=REFRESH_TTL_SECONDS,
            family_id=record["family_id"],
        )

        # Touch the session
        self.store.touch_session(record["session_id"])

        # Get the session to return the CSRF token
        session = self.store.get_session(record["session_id"])

        self.store.audit(
            event_type="token_refresh",
            user_id=record["user_id"],
            ip_address=ip_address,
            detail={"session_id": record["session_id"], "family_id": record["family_id"]},
            success=True,
        )

        return {
            "session_id": record["session_id"],
            "csrf_token": session["csrf_token"] if session else "",
            "refresh_token": new_refresh,
            "expires_at": session["expires_at"] if session else "",
        }

    # ─── Session validation ───

    def validate_session(self, session_id: str) -> dict[str, Any] | None:
        """Validate a session. Returns the user if valid, None otherwise."""
        if not session_id:
            return None
        session = self.store.get_session(session_id)
        if not session:
            return None
        if session["revoked_at"]:
            return None
        from maestro_auth.models import utcnow
        if session["expires_at"] < utcnow():
            return None
        # Touch the session (sliding expiration)
        self.store.touch_session(session["id"])
        user = self.store.get_user(session["user_id"])
        if not user or not user["is_active"]:
            return None
        return {"user": user, "session": session}

    # ─── Cookie helpers ───

    @staticmethod
    def set_session_cookies(response, session_info: dict[str, Any], secure: bool = True) -> None:
        """Set the session, refresh, and CSRF cookies on a response."""
        response.set_cookie(
            SESSION_COOKIE, session_info["session_id"],
            max_age=SESSION_TTL_SECONDS,
            httponly=True, secure=secure, samesite="lax",
            path="/",
        )
        response.set_cookie(
            REFRESH_COOKIE, session_info["refresh_token"],
            max_age=REFRESH_TTL_SECONDS,
            httponly=True, secure=secure, samesite="strict",
            path="/api/auth",
        )
        # CSRF cookie is readable by JS (for double-submit), but HttpOnly would prevent that
        response.set_cookie(
            CSRF_COOKIE, session_info["csrf_token"],
            max_age=SESSION_TTL_SECONDS,
            httponly=False, secure=secure, samesite="lax",
            path="/",
        )

    @staticmethod
    def clear_session_cookies(response) -> None:
        """Clear all session cookies."""
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
        response.delete_cookie(CSRF_COOKIE, path="/")

    # ─── MFA ───

    def verify_mfa(self, user_id: str, code: str) -> bool:
        """Verify an MFA code (TOTP or backup code)."""
        user = self.store.get_user(user_id)
        if not user or not user["mfa_enabled"] or not user["mfa_secret"]:
            return False

        from maestro_auth.models import totp_verify
        if totp_verify(user["mfa_secret"], code):
            self.store.audit(
                event_type="mfa_success",
                user_id=user_id,
                email=user["email"],
                detail={"method": "totp"},
                success=True,
            )
            return True

        # Try backup codes
        if self.store.verify_backup_code(user_id, code):
            self.store.audit(
                event_type="mfa_success",
                user_id=user_id,
                email=user["email"],
                detail={"method": "backup_code"},
                success=True,
            )
            return True

        self.store.audit(
            event_type="mfa_failed",
            user_id=user_id,
            email=user["email"],
            success=False,
        )
        return False
