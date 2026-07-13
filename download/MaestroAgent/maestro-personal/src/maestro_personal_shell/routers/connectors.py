"""Connectors router — OAuth2 connector management + draft approval flow.

Extracted from api.py during the Phase 8 router split. No behavior
changes — same paths, same request/response schemas, same audit logging.

The real moat: passive signal ingestion + commitment-aware drafting.
Drafts NEVER auto-send — every draft requires explicit human approval.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

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
    provider: str  # gmail | slack | github | calendar | whatsapp | facebook | instagram | twitter
    oauth_token: str = ""  # empty in demo mode


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
async def list_connectors(token: str = Depends(verify_token_dep)):
    """List all available connectors with the user's connection state."""
    from maestro_personal_shell.connectors import ConnectorStore
    store = ConnectorStore()
    return {"connectors": store.list_connectors(token)}


# ---------------------------------------------------------------------------
# POST /connectors/{provider}/connect — connect a provider (OAuth or demo)
# ---------------------------------------------------------------------------


@router.post("/connectors/{provider}/connect")
async def connect_provider(provider: str, req: ConnectorConnectRequest, token: str = Depends(verify_token_dep)):
    """Connect a provider (stores OAuth token encrypted).

    For Gmail/Slack/Calendar/GitHub: if OAuth is configured (CLIENT_ID set),
    this endpoint returns the authorization URL — the user visits it, grants
    access, and the provider redirects to /api/connectors/<provider>/oauth/callback
    which completes the connection. If OAuth is NOT configured, stores the
    provided oauth_token directly (demo mode).
    """
    from maestro_personal_shell.connectors import ConnectorStore

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

    store = ConnectorStore()
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


@router.get("/connectors/gmail/oauth/callback")
async def gmail_oauth_callback(
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
    oauth_client = GmailOAuthClient()
    token_data = oauth_client.exchange_code_for_tokens(code)

    if "error" in token_data:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_data['error']}")

    token_json = json.dumps(token_data)
    store = ConnectorStore()
    result = store.connect(user_email, "gmail", token_json)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "connected": True,
        "provider": "gmail",
        "user_email": user_email,
        "message": "Gmail connected successfully. You can now ingest messages and send drafts.",
    }


@router.get("/connectors/slack/oauth/callback")
async def slack_oauth_callback(
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
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "connected": True,
        "provider": "slack",
        "user_email": user_email,
        "message": "Slack connected successfully. You can now ingest DMs and send messages.",
    }


@router.get("/connectors/calendar/oauth/callback")
async def calendar_oauth_callback(
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
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "connected": True,
        "provider": "calendar",
        "user_email": user_email,
        "message": "Calendar connected successfully. Maestro will surface upcoming meetings in the pre-call intelligence panel.",
    }


@router.get("/connectors/github/oauth/callback")
async def github_oauth_callback(
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
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "connected": True,
        "provider": "github",
        "user_email": user_email,
        "message": "GitHub connected successfully. Maestro will ingest assigned issues and can post comments on your behalf (with approval).",
    }


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
    """Create a pending draft for user approval (template formatter — P13 disclosure).

    NOTE (P13): This endpoint takes caller-supplied commitment_text + evidence_refs.
    It is a TEMPLATE FORMATTER, not the real capability. For the real capability
    (deriving commitment + evidence from signal history), use POST /api/drafts/auto.
    """
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
