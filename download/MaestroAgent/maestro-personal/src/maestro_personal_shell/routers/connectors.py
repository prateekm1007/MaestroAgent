"""Connectors router — OAuth2 connector management + draft approval flow."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from maestro_personal_shell.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["connectors"])


# ---------------------------------------------------------------------------
# verify_token lazy proxy (see routers/auth.py for rationale)
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token — decouples this router from api.py's load order."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


# ---------------------------------------------------------------------------
# Pydantic models — moved here from api.py (router-specific)
# ---------------------------------------------------------------------------


class ConnectorConnectRequest(BaseModel):
    # P0-2 fix (audit 2026-07-15): both fields optional. The provider is
    # already in the URL path; the body is only used to pass an oauth_token
    # when one is available. Requiring `provider` in the body caused a 422
    # on every connect attempt where the caller sent an empty body or
    # omitted the redundant field.
    provider: str = ""  # ignored — taken from the URL path
    oauth_token: str = ""  # empty in demo mode / pre-OAuth


class ConnectorDraftRequest(BaseModel):
    provider: str
    recipient: str
    commitment_text: str = ""
    entity: str = ""
    evidence_refs: list[dict[str, Any]] = []


class ConnectorAutoDraftRequest(BaseModel):
    """P13 fix: only provider + recipient — commitment + evidence are DERIVED."""
    provider: str
    recipient: str


class DraftResolutionRequest(BaseModel):
    resolution: str  # approve | deny | use_draft


# ---------------------------------------------------------------------------
# GET /connectors — list all available connectors with the user's state
# ---------------------------------------------------------------------------


@router.get("/connectors")
async def list_connectors(
    experimental: bool = False,
    token: str = Depends(verify_token_dep),
):
    """List all available connectors with the user's connection state."""
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    all_connectors = store.list_connectors(token)

    # F-08 fix (auditor S2): be explicit about demo mode. If Gmail OAuth
    # is not configured, say so clearly in the response instead of implying
    # it should work. This prevents evaluators from wasting time trying to
    # connect Gmail when the OAuth credentials aren't set up.
    _demo_notice = None
    try:
        from maestro_personal_shell.gmail_connector import is_gmail_configured
        if not is_gmail_configured():
            _demo_notice = (
                "Gmail OAuth is not configured in this deployment. "
                "The synthetic inbox (/api/inbox/synthetic) is available "
                "for demo purposes. To enable real Gmail, set "
                "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET environment variables."
            )
    except ImportError:
        _demo_notice = "Gmail connector module not available in this build."

    if experimental:
        return {"connectors": all_connectors, "demo_notice": _demo_notice}
    # Demo surface: only Gmail + Calendar
    _DEMO_CONNECTORS = {"gmail", "calendar"}
    return {
        "connectors": [c for c in all_connectors if c["provider"] in _DEMO_CONNECTORS],
        "demo_notice": _demo_notice,
    }


# ---------------------------------------------------------------------------
# POST /connectors/{provider}/connect — connect a provider (OAuth or demo)
# ---------------------------------------------------------------------------


@router.post("/connectors/{provider}/connect")
@rate_limit("10/minute")  # P0-6: OAuth flow initiation — cap at 10/min per IP (anti-spam)
async def connect_provider(request: Request, provider: str, req: ConnectorConnectRequest | None = None, token: str = Depends(verify_token_dep)):
    """Connect a provider (stores OAuth token encrypted)."""
    req = req or ConnectorConnectRequest()
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()

    # P11 fix (wiring): if the user is ALREADY connected, short-circuit and
    # return {connected: true} instead of re-starting the OAuth flow. The
    # previous version always returned the OAuth URL, so if the user clicked
    # "Connect" again after completing OAuth (e.g. the UI didn't refresh in
    # time), a SECOND OAuth tab would open — confusing and wasteful.
    existing = store.list_connectors(token)
    for row in existing:
        if row.get("provider") == provider and row.get("connected"):
            return {
                "connected": True,
                "provider": provider,
                "already_connected": True,
                "connected_at": row.get("connected_at", ""),
            }

    # Phase B: Gmail OAuth2 flow
    if provider == "gmail" and not req.oauth_token:
        try:
            from maestro_personal_shell.gmail_connector import is_gmail_configured, GmailOAuthClient
            if is_gmail_configured():
                oauth_client = GmailOAuthClient()
                state = f"user={token}"  # carry user identity through the OAuth flow
                auth_url = oauth_client.get_authorization_url(state=state)
                return {"oauth_required": True, "authorization_url": auth_url}
        except ImportError:
            pass  # fall through to demo mode

    # Phase C: Slack OAuth2 flow
    if provider == "slack" and not req.oauth_token:
        try:
            from maestro_personal_shell.slack_connector import is_slack_configured, SlackOAuthClient
            if is_slack_configured():
                oauth_client = SlackOAuthClient()
                state = f"user={token}"
                auth_url = oauth_client.get_authorization_url(state=state)
                return {"oauth_required": True, "authorization_url": auth_url}
        except ImportError:
            pass  # fall through to demo mode

    # Phase E: Calendar OAuth2 flow (read-only)
    if provider == "calendar" and not req.oauth_token:
        try:
            from maestro_personal_shell.calendar_connector import is_calendar_configured, CalendarOAuthClient
            if is_calendar_configured():
                oauth_client = CalendarOAuthClient()
                state = f"user={token}"
                auth_url = oauth_client.get_authorization_url(state=state)
                return {"oauth_required": True, "authorization_url": auth_url}
        except ImportError:
            pass  # fall through to demo mode

    # Phase D: GitHub OAuth2 flow
    if provider == "github" and not req.oauth_token:
        try:
            from maestro_personal_shell.github_connector import is_github_configured, GitHubOAuthClient
            if is_github_configured():
                oauth_client = GitHubOAuthClient()
                state = f"user={token}"
                auth_url = oauth_client.get_authorization_url(state=state)
                return {"oauth_required": True, "authorization_url": auth_url}
        except ImportError:
            pass  # fall through to demo mode

    store = ConnectorStore()  # already created above for the already-connected check

    # S2-03 fix (auditor S2 finding): if OAuth IS configured for this provider,
    # REJECT any direct oauth_token in the body. The only valid path is through
    # the real OAuth flow (authorization URL → provider login → callback). This
    # prevents fake tokens like {"oauth_token": "fake-token"} from producing
    # connected: true. Previously, sending a fake token bypassed the OAuth flow
    # entirely and stored the token directly — a security and trust failure.
    if req.oauth_token:
        # Check if OAuth is configured for this provider
        _oauth_configured = False
        try:
            if provider == "gmail":
                from maestro_personal_shell.gmail_connector import is_gmail_configured
                _oauth_configured = is_gmail_configured()
            elif provider == "calendar":
                from maestro_personal_shell.calendar_connector import is_calendar_configured
                _oauth_configured = is_calendar_configured()
            elif provider == "slack":
                from maestro_personal_shell.slack_connector import is_slack_configured
                _oauth_configured = is_slack_configured()
            elif provider == "github":
                from maestro_personal_shell.github_connector import is_github_configured
                _oauth_configured = is_github_configured()
        except ImportError as e:
            logger.debug("is_github_configured failed: %s", e)
        if _oauth_configured:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Direct token assignment is not allowed for '{provider}'. "
                    f"This connector requires OAuth — click 'Connect' to be redirected "
                    f"to the provider's authorization page."
                ),
            )

    # Phase F: Work Email (IMAP) — direct credentials, NOT OAuth.
    # The user provides their work email + app password + IMAP host.
    # We VERIFY the connection works before storing — no fake "connected".
    if provider == "work_email":
        if not req.oauth_token:
            raise HTTPException(
                status_code=400,
                detail="Work email requires IMAP credentials (host, port, username, app_password).",
            )
        try:
            cred_data = json.loads(req.oauth_token)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid credential format — expected JSON with host, username, app_password.",
            )

        host = cred_data.get("host", "")
        port = cred_data.get("port", 993)
        username = cred_data.get("username", "")
        password = cred_data.get("password", "") or cred_data.get("app_password", "")

        if not host or not username or not password:
            raise HTTPException(
                status_code=400,
                detail="Work email requires host, username, and app_password.",
            )

        # VERIFY the IMAP connection actually works before storing.
        # This is the critical honesty fix: no fake "connected" if the
        # credentials don't actually authenticate.
        try:
            import imaplib
            conn = imaplib.IMAP4_SSL(host, port)
            conn.login(username, password)
            conn.select("INBOX")
            conn.logout()
        except imaplib.IMAP4.error as e:
            raise HTTPException(
                status_code=401,
                detail=f"IMAP connection failed: {e}. Check app password / enable IMAP / 2FA settings.",
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"IMAP connection error: {e}. Check host and port.",
            )

        # Connection verified — store the credentials (encrypted via ConnectorStore)
        # The password is NEVER logged. ConnectorStore._encrypt() handles encryption.
        result = store.connect(token, provider, req.oauth_token)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        # Trigger initial ingest
        try:
            shell = build_shell(user_email=token)
            ingest_result = store.ingest(token, "work_email", shell=shell)
            result["ingested"] = ingest_result.get("ingested", 0)
        except Exception as e:
            logger.warning("Work email initial ingest failed (non-fatal): %s", e)
            result["ingested"] = 0

        return result

    # P0 honesty fix: if no OAuth is configured AND no oauth_token is provided,
    # we must NOT return connected: True. No demo-mode fallback — fail closed.
    if not req.oauth_token:
        raise HTTPException(
            status_code=400,
            detail=(
                f"OAuth is not configured for '{provider}'. "
                f"Ask your administrator to configure this connector, "
                f"or see docs/CONNECTOR_OAUTH_SETUP.md for setup instructions."
            ),
        )

    result = store.connect(token, provider, req.oauth_token)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# OAuth callbacks — exchange code for tokens, store encrypted
# ---------------------------------------------------------------------------


def _extract_user_email(state: str) -> str:
    """Extract user_email from the OAuth state parameter."""
    if "user=" in state:
        return state.split("user=", 1)[1]
    return ""


def _oauth_success_page(provider: str) -> HTMLResponse:
    """Return an HTML page that closes the popup or redirects back to the app."""
    return HTMLResponse(content=f'''
    <html>
    <body style="font-family: -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #F8F0DD;">
    <div style="text-align: center;">
    <h1 style="color: #1A1A1A;">✅ {provider.title()} Connected!</h1>
    <p style="color: #666; margin-top: 16px;">You can close this tab and return to Maestro.</p>
    <script>
      // Try to close the popup window
      setTimeout(function() {{
        window.close();
      }}, 2000);
      // If can't close (not a popup), redirect back to the app
      setTimeout(function() {{
        window.location.href = window.location.origin.replace('8766', '8081');
      }}, 3000);
    </script>
    </div>
    </body>
    </html>
    ''')

def _oauth_error_page(error: str) -> HTMLResponse:
    """Return an HTML error page for OAuth failures."""
    return HTMLResponse(content=f'''
    <html>
    <body style="font-family: -apple-system, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #F8F0DD;">
    <div style="text-align: center;">
    <h1 style="color: #CC0000;">❌ Connection Failed</h1>
    <p style="color: #666; margin-top: 16px;">{error}</p>
    <p style="color: #999; margin-top: 8px;">Close this tab and try again.</p>
    <script>setTimeout(function() {{ window.close(); }}, 5000);</script>
    </div>
    </body>
    </html>
    ''', status_code=400)


def _oauth_response(
    request: Request,
    provider: str,
    user_email: str,
    success: bool = True,
    error: str = "",
):
    """Content-negotiated OAuth callback response.

    Real OAuth callbacks are *browser redirects* — the OAuth provider sends
    the user back to /api/connectors/<provider>/oauth/callback in their
    browser, which expects an HTML page that closes the popup or redirects
    back to the app. API clients (mobile app, tests, programmatic callers)
    expect JSON with the connection result.

    Use the Accept header to distinguish:
      - ``Accept: text/html``  → HTML success/error page (browser)
      - anything else          → JSON ``{connected, provider, user_email, message}``

    P14 fix (4-round-old pre-existing failure): the previous version returned
    HTML unconditionally, so every API client (including tests) got a
    ``JSONDecodeError`` when trying to parse the response.
    """
    accept = request.headers.get("accept", "").lower()
    if "text/html" in accept:
        # Real browser — return the HTML success/error page
        return _oauth_success_page(provider) if success else _oauth_error_page(error)
    # API client / test — return JSON
    if success:
        # Pull the connector's descriptive text so the mobile app can show
        # what the connection enables (e.g. "Ingest upcoming meetings, feed
        # into pre-call intelligence" for Calendar).
        from maestro_personal_shell.connectors import SUPPORTED_CONNECTORS
        info = SUPPORTED_CONNECTORS.get(provider, {})
        ingest = info.get("ingest_description", "")
        write = info.get("write_description", "")
        message = " | ".join(part for part in (ingest, write) if part)
        return {
            "connected": True,
            "provider": provider,
            "user_email": user_email,
            "message": message,
        }
    raise HTTPException(status_code=400, detail=error)


@router.get("/connectors/gmail/oauth/callback")
async def gmail_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """Gmail OAuth2 callback — exchanges authorization code for tokens."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    from maestro_personal_shell.connectors import ConnectorStore
    from maestro_personal_shell.gmail_connector import GmailOAuthClient, is_gmail_configured

    if not is_gmail_configured():
        raise HTTPException(status_code=400, detail="Gmail OAuth not configured")

    user_email = _extract_user_email(state)
    logger.info("[gmail-callback] state_user=%r", user_email)
    oauth_client = GmailOAuthClient()
    token_data = oauth_client.exchange_code_for_tokens(code)

    if "error" in token_data:
        logger.error("[gmail-callback] token exchange failed for user=%r: %s", user_email, token_data['error'])
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_data['error']}")

    token_json = json.dumps(token_data)
    store = ConnectorStore()
    result = store.connect(user_email, "gmail", token_json)
    if "error" in result:
        logger.error("[gmail-callback] store.connect failed for user=%r: %s", user_email, result["error"])
        return _oauth_response(request, "gmail", user_email, success=False, error=result["error"])

    logger.info("[gmail-callback] tokens stored for user=%r", user_email)

    # Sync-on-connect: immediately ingest recent emails after OAuth success.
    ingest_result = None
    try:
        from maestro_personal_shell.api import build_shell
        shell = build_shell(user_email=user_email)
        ingest_result = store.ingest(user_email, "gmail", shell=shell)
        logger.info("[gmail-callback] ingest for user=%r: %s", user_email, ingest_result)
    except Exception as e:
        logger.error("Gmail sync-on-connect failed (non-fatal — tokens stored): %s", e)
        ingest_result = {"error": str(e)}

    return _oauth_response(request, "gmail", user_email, success=True)


@router.get("/connectors/slack/oauth/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """Slack OAuth2 callback — exchanges authorization code for tokens."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    from maestro_personal_shell.connectors import ConnectorStore
    from maestro_personal_shell.slack_connector import SlackOAuthClient, is_slack_configured

    if not is_slack_configured():
        raise HTTPException(status_code=400, detail="Slack OAuth not configured")

    user_email = _extract_user_email(state)
    oauth_client = SlackOAuthClient()
    token_data = oauth_client.exchange_code_for_tokens(code)

    if "error" in token_data:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_data['error']}")

    token_json = json.dumps(token_data)
    store = ConnectorStore()
    result = store.connect(user_email, "slack", token_json)
    if "error" in result:
        return _oauth_response(request, "slack", user_email, success=False, error=result["error"])

    return _oauth_response(request, "slack", user_email, success=True)


@router.get("/connectors/calendar/oauth/callback")
async def calendar_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """Google Calendar OAuth2 callback — exchanges authorization code for tokens."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    from maestro_personal_shell.connectors import ConnectorStore
    from maestro_personal_shell.calendar_connector import CalendarOAuthClient, is_calendar_configured

    if not is_calendar_configured():
        raise HTTPException(status_code=400, detail="Calendar OAuth not configured")

    user_email = _extract_user_email(state)
    oauth_client = CalendarOAuthClient()
    token_data = oauth_client.exchange_code_for_tokens(code)

    if "error" in token_data:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_data['error']}")

    token_json = json.dumps(token_data)
    store = ConnectorStore()
    result = store.connect(user_email, "calendar", token_json)
    if "error" in result:
        return _oauth_response(request, "calendar", user_email, success=False, error=result["error"])

    return _oauth_response(request, "calendar", user_email, success=True)


@router.get("/connectors/github/oauth/callback")
async def github_oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
):
    """GitHub OAuth2 callback — exchanges authorization code for tokens."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    from maestro_personal_shell.connectors import ConnectorStore
    from maestro_personal_shell.github_connector import GitHubOAuthClient, is_github_configured

    if not is_github_configured():
        raise HTTPException(status_code=400, detail="GitHub OAuth not configured")

    user_email = _extract_user_email(state)
    oauth_client = GitHubOAuthClient()
    token_data = oauth_client.exchange_code_for_tokens(code)

    if "error" in token_data:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_data['error']}")

    token_json = json.dumps(token_data)
    store = ConnectorStore()
    result = store.connect(user_email, "github", token_json)
    if "error" in result:
        return _oauth_response(request, "github", user_email, success=False, error=result["error"])

    return _oauth_response(request, "github", user_email, success=True)


# ---------------------------------------------------------------------------
# DELETE /connectors/{provider} — disconnect a provider
# ---------------------------------------------------------------------------


@router.delete("/connectors/{provider}")
async def disconnect_provider(provider: str, token: str = Depends(verify_token_dep)):
    """Disconnect a provider (deletes the token, keeps audit history)."""
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    result = store.disconnect(token, provider)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# POST /connectors/{provider}/ingest — pull messages + ingest as signals
# ---------------------------------------------------------------------------


@router.post("/connectors/{provider}/ingest")
async def ingest_connector(provider: str, token: str = Depends(verify_token_dep)):
    """Pull messages from a connector and ingest commitments as signals."""
    from maestro_personal_shell.connectors import ConnectorStore
    from maestro_personal_shell.api import build_shell
    store = ConnectorStore()
    shell = build_shell(user_email=token)
    result = store.ingest(token, provider, shell=shell)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# GET /connectors/audit — connector + draft audit log
# ---------------------------------------------------------------------------


@router.get("/connectors/audit")
async def connector_audit_log(token: str = Depends(verify_token_dep), limit: int = 50):
    """Get the connector + draft audit log for the current user."""
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    return {"audit": store.get_audit_log(token, limit=limit)}


# ---------------------------------------------------------------------------
# Drafts — pending draft creation + approval flow
# ---------------------------------------------------------------------------


@router.post("/drafts")
async def create_draft(req: ConnectorDraftRequest, token: str = Depends(verify_token_dep)):
    """Create a pending draft for user approval."""
    from maestro_personal_shell.connectors import ConnectorStore, ConnectorDraftGenerator
    store = ConnectorStore()
    gen = ConnectorDraftGenerator(shell=None)
    draft_data = gen.generate_draft(
        provider=req.provider,
        recipient=req.recipient,
        commitment={"text": req.commitment_text, "entity": req.entity},
        evidence_refs=req.evidence_refs,
    )
    result = store.create_draft(
        user_email=token,
        provider=draft_data["provider"],
        recipient=draft_data["recipient"],
        subject=draft_data["subject"],
        body=draft_data["body"],
        commitment_ref=draft_data["commitment_ref"],
        evidence_refs=draft_data["evidence_refs"],
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result


@router.post("/drafts/auto")
async def create_auto_draft(req: ConnectorAutoDraftRequest, token: str = Depends(verify_token_dep)):
    """DERIVE a draft from the user's signal history — the real capability (P13 fix).

    Only takes provider + recipient. Maestro DERIVES:
      1. The commitment (by searching the user's signals for commitments to this recipient)
      2. The evidence_refs (via keyword match + FTS5 retrieval on the recipient name)

    If no commitments are found for the recipient, returns 404 with guidance.
    """
    from maestro_personal_shell.connectors import ConnectorStore, ConnectorDraftGenerator
    from maestro_personal_shell.api import build_shell
    store = ConnectorStore()
    shell = build_shell(user_email=token)
    gen = ConnectorDraftGenerator(shell=shell)
    draft_data = gen.generate_auto_draft(
        provider=req.provider,
        recipient=req.recipient,
        shell=shell,
        user_email=token,
    )
    if "error" in draft_data:
        raise HTTPException(status_code=404, detail=draft_data["error"])

    result = store.create_draft(
        user_email=token,
        provider=draft_data["provider"],
        recipient=draft_data["recipient"],
        subject=draft_data["subject"],
        body=draft_data["body"],
        commitment_ref=draft_data["commitment_ref"],
        evidence_refs=draft_data["evidence_refs"],
    )
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    # Attach derivation metadata so the UI can show "derived from your signals"
    result["derived"] = draft_data.get("derived", False)
    result["commitment_source"] = draft_data.get("commitment_source", "")
    result["evidence_count"] = draft_data.get("evidence_count", 0)
    # P11 fix (wiring): pass through the LLM/style flags so the mobile app
    # can show "AI-generated in your writing style". Previously these were
    # computed by generate_intelligent_draft but dropped here.
    result["llm_generated"] = draft_data.get("llm_generated", False)
    result["style_applied"] = draft_data.get("style_applied", False)
    return result


@router.get("/drafts")
async def list_drafts(token: str = Depends(verify_token_dep), status: str = "pending"):
    """List drafts for the current user, optionally filtered by status."""
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    return {"drafts": store.list_drafts(token, status=status)}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, token: str = Depends(verify_token_dep)):
    """Get a single draft by ID."""
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    draft = store.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    return draft


@router.post("/drafts/{draft_id}/resolve")
async def resolve_draft(draft_id: str, req: DraftResolutionRequest, token: str = Depends(verify_token_dep)):
    """Resolve a draft: approve (send), deny (discard), or use_draft (open in compose).

    The approval flow is the trust mechanism — Maestro NEVER auto-sends.
    Every draft requires explicit human approval.
    """
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    result = store.resolve_draft(draft_id, req.resolution, user_email=token)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
