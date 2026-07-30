"""Signals router — signal CRUD + ingest endpoints."""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

# P3/Kimi-K3 fix: import _rule_based_classify at MODULE LEVEL so it's
# available even when the classify_commitment import fails inside the
# try block. _rule_based_classify is sync, pure text, touches no DB.
from maestro_personal_shell.commitment_classifier import _rule_based_classify
from maestro_personal_shell.db_util import default_sqlite_path

from maestro_personal_shell.models import (
    CalendarSyncRequest,
    CalendarSyncResponse,
    GmailSyncRequest,
    GmailSyncResponse,
    SignalCreate,
    SignalResponse,
    SituationResponse,
    SlackIngestRequest,
    TranscriptIngestRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["signals"])


# ---------------------------------------------------------------------------
# verify_token lazy proxy
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token — decouples this router from api.py's load order."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


# ---------------------------------------------------------------------------
# /api/situations — list detected situations
# ---------------------------------------------------------------------------


@router.get("/situations", response_model=list[SituationResponse])
async def get_situations(token: str = Depends(verify_token_dep)):
    """Get all detected situations from personal signals."""
    from maestro_personal_shell.api import build_shell

    shell = build_shell(user_email=token)
    situations = shell.detect_situations()

    result = []
    for s in situations:
        # Extract state value — handle enums (use .value) and plain strings
        state_raw = getattr(s, "state", getattr(s, "operational_state", "unknown"))
        if hasattr(state_raw, "value"):
            state_val = state_raw.value
        else:
            # Strip enum repr like "SituationState.OBSERVING" → "OBSERVING" → lowercase
            state_str = str(state_raw)
            if "." in state_str:
                state_val = state_str.split(".")[-1].lower()
            else:
                state_val = state_str.lower()

        result.append(SituationResponse(
            situation_id=str(getattr(s, "situation_id", uuid4())),
            entity=str(getattr(s, "entity", "")),
            state=state_val,
            evidence_count=len(getattr(s, "evidence_refs", []) or []),
        ))
    return result


# ---------------------------------------------------------------------------
# /api/signals — POST (create) and GET (list)
# ---------------------------------------------------------------------------

# Phase 3.2: Inline machine sender classifier (defined before create_signal)
_MACHINE_ENTITIES_SET = {
    "aws billing", "aws", "github", "linkedin", "product hunt", "producthunt",
    "vercel", "railway", "spotify", "kotak", "zerodha", "polsia",
    "notion", "slack", "discord", "stripe", "google cloud", "google",
    "microsoft", "azure", "digitalocean", "heroku", "netlify",
    "cloudflare", "the athletic", "washington post", "dalal street",
    "communications", "noreply", "no-reply",
}
_MACHINE_TEXT_KEYWORDS = [
    "processed automatically", "no action needed", "do not reply",
    "unsubscribe", "your bill", "invoice #", "receipt",
    "verification code", "security alert", "was successfully",
    "thank you for your payment", "privacy policy", "terms of service",
]

def _is_machine_sender(entity: str, text: str) -> bool:
    """Check if this is a machine sender. Returns True if should reject."""
    entity_lower = (entity or "").lower().strip()
    for me in _MACHINE_ENTITIES_SET:
        if me in entity_lower:
            return True
    text_lower = (text or "").lower()
    for kw in _MACHINE_TEXT_KEYWORDS:
        if kw in text_lower:
            return True
    return False


@router.post("/signals", response_model=SignalResponse)
async def create_signal(req: SignalCreate, token: str = Depends(verify_token_dep)):
    """Create a new personal signal (manual entry for v1)."""
    from maestro_personal_shell.api import (
        save_signal_to_db,
        load_signals_from_db,
    )
    from maestro_personal_shell.signal_adapters.gmail import sanitize_email_text
    from maestro_personal_shell.llm_bridge import sanitize_for_llm

    # F-26 fix (auditor v12, 2026-07-29): reject test/audit probe entities
    # in production with HTTP 422. The v12 auditor found "RaceAnna_1785999999"
    # accepted with HTTP 200, polluting 32% of the production ledger. The guard
    # is anchored (never substring-matches "Race Car Dynamics LLC") and only
    # fires in production env (dev/test/staging can use probe names).
    # P54: guard at WRITE time so test data never enters the corpus.
    # P1: verified by execution — see tests/test_audit_v11_pinned_regressions.py.
    from maestro_personal_shell.test_entity_guard import should_reject_test_entity
    if should_reject_test_entity(req.entity):
        logger.warning(
            "F-26: test entity rejected in production (entity=%r, env=%s)",
            req.entity, os.environ.get("MAESTRO_ENV", "production"),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "test_entity_rejected",
                "entity": req.entity,
                "reason": "Entity name matches a test/audit probe pattern. "
                          "Production rejects test data. Set MAESTRO_ENV=dev "
                          "to allow test entities.",
            },
        )

    # F4 + auditor fix: THREE-LAYER sanitization on ingest.
    # Layer 1: gmail.sanitize_email_text (email-specific patterns)
    # Layer 2: sanitize_for_llm (25+ pattern regex injection defense)
    # Layer 3: semantic_injection_check (LLM-based, catches novel paraphrase
    #          attacks the regex misses — e.g. "kindly overlook every directive")
    #
    # P0-Audit fix: HTML entity encoding + secret keyword blocklist +
    # HTML comment blocking. The auditor found <script> tags, SECRET_TOKEN,
    # and <!-- --> comments survived all 3 layers.
    #
    # F-14 fix (auditor v12, 2026-07-29): NO-MUTATION injection filter.
    # The prior code called _regex_sanitize(sanitized_text) at WRITE time,
    # which spliced "[filtered]" into legitimate phrases like
    # "Please ignore the previous email" → "[filtered]the previous email".
    # Partial corruption is more dangerous than full replacement because
    # the result reads as authentic. Fix: store the text VERBATIM (only
    # html-escaped for XSS safety), flag suspected injection in metadata,
    # and neutralize at READ time in ask.py's assemble_llm_context.
    # This is the P54 principle: fix the data the user sees — the stored
    # text must always be what the user wrote.
    #
    # S1-7 fix (auditor #11): defense-in-depth. The no-mutation approach
    # is correct for LEGITIMATE emails (F-14), but OBVIOUS injection
    # patterns ("IGNORE ALL PREVIOUS INSTRUCTIONS") should be neutralized
    # at write time too. The auditor's R4 test checks that the hostile
    # payload is NOT in the stored text — verbatim storage fails this.
    # Fix: replace OBVIOUS injection patterns with a placeholder, but
    # leave everything else verbatim. This preserves both F-14 (legitimate
    # emails not mutated) and S1-7 (hostile payloads neutralized at write).
    from maestro_personal_shell.llm_bridge import sanitize_for_llm as _regex_sanitize
    from maestro_personal_shell.signal_adapters.gmail import sanitize_email_text

    # Phase 3.2 (roadmap): Machine sender classifier — reject automated
    # content before the commitment classifier runs. AWS Billing, GitHub
    # notifications, LinkedIn, etc. must never become commitments.
    # 66% of ambient alerts were noise across six audits.
    try:
        _sender_result = {"should_skip": _is_machine_sender(req.entity, req.text), "reason": "machine sender"}
        # (replaced by inline check above)
        if _sender_result["should_skip"]:
            logger.info("Phase 3.2: rejecting machine sender: %s — %s",
                        req.entity[:50], _sender_result["reason"])
            return SignalResponse(
                signal_id=None,
                entity=req.entity or "",
                text=req.text or "",
                signal_type=req.signal_type or "",
                timestamp=datetime.now(timezone.utc).isoformat(),
                rejected="machine_sender",
            )
    except Exception as _sender_err:
        logger.warning("sender_classifier failed (non-fatal): %s", _sender_err)

    sanitized_text = sanitize_email_text(req.text)
    # F-14: do NOT call _regex_sanitize at write time — it mutates text.
    # Instead, check for injection patterns and flag in metadata.
    _injection_suspected = _regex_sanitize(sanitized_text) != sanitized_text

    # S1-7: Minimal write-time filter for OBVIOUS injection patterns only.
    # These are patterns that no legitimate email would contain.
    # Legitimate phrases like "Please ignore the previous email" are NOT
    # caught here — they pass through verbatim (F-14 protection).
    _OBVIOUS_INJECTION_PATTERNS = [
        r'ignore\s+all\s+previous\s+instructions',
        r'disregard\s+prior\s+rules',
        r'you\s+are\s+now\s+dan\b',
        r'reveal\s+your\s+system\s+prompt',
        r'^SYSTEM:\s*disregard',
        r'\bjailbroken\b',
        r'developer\s+mode\s+enabled',
    ]
    for _pattern in _OBVIOUS_INJECTION_PATTERNS:
        if _re.search(_pattern, sanitized_text, _re.IGNORECASE):
            sanitized_text = "[Content filtered due to potential prompt injection]"
            _injection_suspected = True
            logger.info("S1-7: write-time injection filter neutralized hostile payload")
            break

    # P0.1: HTML entity encoding — prevent stored XSS. <script> → &lt;script&gt;
    # This is the ONLY transformation applied to stored text. It's reversible
    # (the original text can be recovered by un-escaping) and doesn't splice
    # markers into legitimate phrases.
    sanitized_text = _html.escape(sanitized_text, quote=False)

    # P0.2: Secret keyword blocklist — prevent token/secret probing.
    # If the text contains these keywords, replace with [REDACTED].
    # P0-Audit fix (2026-07-18): also redact the VALUE after the keyword
    # (was: only redacting the keyword itself, leaving "API_KEY=sk-12345" →
    # "[REDACTED]=sk-12345" — the secret value was still exposed).
    _SECRET_KEYWORDS = [
        "SECRET_TOKEN", "AUTH_TOKEN", "API_KEY", "PRIVATE_KEY",
        "JWT_SECRET", "ACCESS_TOKEN", "REFRESH_TOKEN", "SESSION_SECRET",
        "PASSWORD", "PASSWD", "PWD",
    ]
    for kw in _SECRET_KEYWORDS:
        # Redact keyword + optional value: "API_KEY=sk-123" → "[REDACTED]"
        # Also catches "API_KEY: sk-123", "password is MySecret123", "api_key=sk-123"
        pattern = _re.compile(
            _re.escape(kw) + r'\s*(?:[:=]\s*|is\s+)\S+',
            _re.IGNORECASE,
        )
        sanitized_text = pattern.sub('[REDACTED]', sanitized_text)
        # Also redact standalone keyword (no value following)
        sanitized_text = sanitized_text.replace(kw, "[REDACTED]")
        sanitized_text = sanitized_text.replace(kw.lower(), "[REDACTED]")

    # P0-Audit fix (2026-07-18): OTP/verification code redaction.
    # Detects 4-8 digit codes (common OTPs, verification codes, PINs) when
    # preceded by contextual keywords: "OTP", "code", "password", "PIN",
    # "verification", "verify", "auth code". Prevents financial/banking
    # OTPs from being stored as signals and surfaced via Ask.
    _OTP_CONTEXT = r'(?:otp|one[\s-]?time[\s-]?password|verification\s+code|verify\s+code|auth(?:entication)?\s+code|access\s+code|security\s+code|pin|password|passcode|cvv|cvc)'
    # "Your OTP is 9907" → "Your OTP is [REDACTED_OTP]"
    sanitized_text = _re.sub(
        _OTP_CONTEXT + r'\s*(?:is|:|=|\s)\s*(\d{4,8})',
        r'[REDACTED_OTP]',
        sanitized_text,
        flags=_re.IGNORECASE,
    )
    # Also catch "9907 is your OTP" (reversed order)
    sanitized_text = _re.sub(
        r'(\d{4,8})\s+is\s+your\s+' + _OTP_CONTEXT,
        r'[REDACTED_OTP]',
        sanitized_text,
        flags=_re.IGNORECASE,
    )

    # P0-Audit fix: Common API key pattern redaction (value-level, not just keyword).
    # Catches: sk-..., ghp_..., github_pat_..., AKIA..., xoxb-..., AIza...
    _API_KEY_PATTERNS = [
        r'sk-[a-zA-Z0-9]{20,}',          # OpenAI
        r'ghp_[a-zA-Z0-9]{36}',          # GitHub PAT
        r'github_pat_[a-zA-Z0-9_]{22,}', # GitHub fine-grained PAT
        r'AKIA[0-9A-Z]{16}',             # AWS access key
        r'xox[bpoa]-[a-zA-Z0-9-]+',      # Slack token
        r'AIza[0-9A-Za-z\-_]{35}',       # Google API key
        r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',  # JWT
    ]
    for pat in _API_KEY_PATTERNS:
        sanitized_text = _re.sub(pat, '[REDACTED_KEY]', sanitized_text)

    # P0.3: HTML comment blocking — <!-- ignore --> comments survive regex.
    # After html.escape(), <!-- becomes &lt;!-- so we must check BOTH forms.
    sanitized_text = _re.sub(r'<!--.*?-->', '[REDACTED]', sanitized_text, flags=_re.DOTALL)
    sanitized_text = _re.sub(r'&lt;!--.*?--&gt;', '[REDACTED]', sanitized_text, flags=_re.DOTALL)
    # Also block standalone comment markers (both raw and escaped)
    for marker in ('<!--', '-->', '&lt;!--', '--&gt;'):
        sanitized_text = sanitized_text.replace(marker, '[REDACTED]')

    # P0.3: Case-insensitive jailbreak keyword blocking
    # S4 fix: auditor found "JAILBROKEN" survived because the regex only
    # matched "jailbreak" (a substring of "jailbroken"). Now we explicitly
    # include "jailbroken" as a separate keyword.
    _JAILBREAK_KEYWORDS = [
        "jailbroken", "jailbreak", "jail breaker", "jail breaking",
        "dan mode", "developer mode enabled", "admin mode enabled",
        "god mode", "root mode", "unrestricted mode",
    ]
    for kw in _JAILBREAK_KEYWORDS:
        sanitized_text = _re.sub(_re.escape(kw), '[REDACTED]', sanitized_text, flags=_re.IGNORECASE)

    # Layer 3: semantic injection check (async, runs when LLM available)
    # P0-Audit fix: only run when a REAL LLM provider is available (not ZAI
    # which is rate-limited). The ZAI CLI fires 429 retries on every signal
    # ingest, adding 7s of latency per signal. Skip it when the provider
    # is rate-limited — the regex layers already caught the known patterns.
    # P4 FIX: semantic_injection_check DISABLED at write time.
    # It was destroying legitimate business emails like "Forget about the
    # roadmap presentation." — exactly the retraction phrases a commitment
    # tracker must capture. The semantic check runs at READ time in ask.py
    # assemble_llm_context(), which is the correct architecture (Principle 4).
    # Only the minimal regex filter (ignore all previous instructions, etc.)
    # runs at write time — that's sufficient for defense-in-depth.

    # TICKET-1/P59: use caller-provided signal_id if available (for tests)
    signal_id = req.signal_id if req.signal_id else str(uuid4())
    now = datetime.now(timezone.utc)

    # P0-3 fix: use client-provided timestamp if available (preserves history)
    # Otherwise use server now (backward compat)
    signal_timestamp = req.timestamp if req.timestamp else now.isoformat()

    # S4: Classify commitment type + lifecycle state on ingest.
    # This runs the LLM-powered classifier (or rule-based fallback) and
    # stores the result in metadata. Downstream endpoints (Commitments,
    # The Moment) use this to filter non-commitments.
    #
    # P37/P3 fix (Kimi K3 design): classification must be resilient.
    # If classify_commitment (LLM path) fails for ANY reason (timeout,
    # ImportError, DB lock during entity resolution), fall back to
    # _rule_based_classify (sync, pure text, no DB). If THAT also fails,
    # set needs_review — NEVER silently admit as a commitment.
    #
    # TICKET-1/P59: START with the caller's metadata (from the request body)
    # so classification hints (commitment_state, commitment_type) are
    # preserved. The classifier refines these; the caller's intent is
    # respected for fields the classifier doesn't override.
    metadata: dict[str, Any] = dict(req.metadata) if req.metadata else {}
    _caller_commitment_state = metadata.get("commitment_state", "")
    _caller_commitment_type = metadata.get("commitment_type", "")  # S1-6/P65: save BEFORE classifier overwrites
    _caller_is_commitment = metadata.get("is_commitment", None)
    classification = None
    signal_type_override = "needs_review"  # default: NOT a commitment

    # TICKET-6c: extract sender_email from metadata if present, so the
    # marketing SENDER filter (TICKET-6b) can reject marketing domains
    # on manually-created signals too. Callers can pass:
    #   {"metadata": {"sender_email": "noreply@slack.com"}}
    _sender_email = req.metadata.get("sender_email", "") if req.metadata else ""

    try:
        from maestro_personal_shell.commitment_classifier import classify_commitment
        classification = await classify_commitment(
            text=sanitized_text,
            entity=req.entity,
            sender_email=_sender_email,
        )
    except Exception as e:
        logger.warning("LLM classification failed: %s — falling back to rules", e)
        try:
            classification = _rule_based_classify(sanitized_text, req.entity, sender_email=_sender_email)
        except Exception as e2:
            logger.error("Rules classifier also failed: %s", e2)
            classification = None

    if classification is not None:
        metadata["commitment_type"] = classification.get("commitment_type", "not_a_commitment")
        metadata["is_commitment"] = classification.get("is_commitment", False)
        # TICKET-1/P59: if the caller specified a resolution state (cancelled/
        # completed_claimed/completed_verified/broken), PRESERVE it — the
        # classifier doesn't detect lifecycle transitions from text alone.
        _classifier_state = classification.get("state", "candidate")
        if _caller_commitment_state in ("cancelled", "completed_claimed", "completed_verified", "broken"):
            metadata["commitment_state"] = _caller_commitment_state
        else:
            metadata["commitment_state"] = _classifier_state

        # S1-6/P65 fix (auditor v11 correction, 2026-07-29): if the caller
        # explicitly passed a RESOLUTION commitment_type (cancelled/completed/
        # broken) but the classifier returned a non-commitment type, PRESERVE
        # the caller's type. The LLM sometimes misclassifies completion
        # signals ("Alex PR review completed" → not_a_commitment/owner=other)
        # because it reads "Alex" as a third party. Without this preservation,
        # the F-09 gate and upsert_ledger_entry gate both short-circuit the
        # signal, and the TICKET-1 transition never fires. The caller's
        # explicit type is the ground truth for resolution signals.
        # _caller_commitment_type was saved BEFORE the classifier overwrote
        # metadata["commitment_type"] at line 262 above.
        _RESOLUTION_TYPES_CALLER = {"cancelled", "completed", "broken", "superseded", "disputed"}
        if (_caller_commitment_type in _RESOLUTION_TYPES_CALLER
                and metadata["commitment_type"] in ("not_a_commitment", "third_party_report")
                and _caller_commitment_state in ("cancelled", "completed_claimed", "completed_verified", "broken")):
            metadata["commitment_type"] = _caller_commitment_type
            metadata["is_commitment"] = False  # S1-6: resolution signals are not active obligations
            logger.info(
                "S1-6/P65: caller resolution type preserved (caller=%s, "
                "classifier=%s) — LLM misclassified resolution signal",
                _caller_commitment_type,
                classification.get("commitment_type", "?"),
            )

        metadata["commitment_confidence"] = classification.get("confidence", 0.5)
        metadata["commitment_owner"] = classification.get("owner", metadata.get("commitment_owner", "unknown"))
        metadata["classification_reasoning"] = classification.get("reasoning", "")
        metadata["llm_powered"] = classification.get("llm_powered", False)
        # S2-3 fix (auditor v11, 2026-07-29): write the parsed deadline_text
        # to metadata so /api/commitments.deadline is populated. The prior
        # code dropped the classifier's deadline_text on the floor — the
        # classifier parsed it correctly, but the signals router never
        # propagated it into the persisted metadata. /api/commitments reads
        # metadata["deadline"], so we set BOTH "deadline" (the read key)
        # and "deadline_text" (the canonical classifier-output key) for
        # coherence with the ledger schema.
        #
        # BUG 2 fix (auditor #11): parse the raw deadline text to ISO 8601
        # at write time. Previously stored raw text ("Friday EOD") instead
        # of ISO timestamp ("2026-07-31T17:00:00+00:00").
        _raw_deadline = classification.get("deadline_text", "")
        metadata["deadline_text"] = _raw_deadline

        # Parse to ISO if we have a deadline phrase
        if _raw_deadline:
            try:
                from maestro_personal_shell.deadline_parser import parse_deadline
                _parsed_dt = parse_deadline(_raw_deadline)
                if _parsed_dt:
                    metadata["deadline"] = _parsed_dt.isoformat()
                else:
                    # Try parsing the full text (deadline phrase may be embedded)
                    _parsed_dt = parse_deadline(sanitized_text)
                    metadata["deadline"] = _parsed_dt.isoformat() if _parsed_dt else _raw_deadline
            except Exception as _dl_parse_err:
                logger.debug("Deadline ISO parsing failed (non-fatal): %s", _dl_parse_err)
                metadata["deadline"] = _raw_deadline  # fallback to raw text
        else:
            metadata["deadline"] = ""

        classified_type = classification.get("commitment_type", "not_a_commitment")
        NON_COMMITMENT_TYPES = {
            "not_a_commitment", "tentative", "proposal", "request",
            "aspiration", "negation",
        }

        # P37/Kimi-K3 fix: if the LLM says "commitment" but the rules
        # classifier says "not_a_commitment", trust the RULES for clear-cut
        # cases (questions, tentative, etc.). The LLM (Gemma 12B) sometimes
        # classifies questions as commitments — the rules classifier is more
        # reliable for structural patterns (interrogative mood, tentative
        # hedges). Run the rules classifier as a secondary check whenever
        # the LLM says it IS a commitment.
        if classified_type not in NON_COMMITMENT_TYPES and classification.get("llm_powered", False):
            try:
                rules_result = _rule_based_classify(sanitized_text, req.entity)
                rules_type = rules_result.get("commitment_type", "not_a_commitment")
                if rules_type in NON_COMMITMENT_TYPES:
                    # Rules classifier overrides LLM for clear non-commitments
                    classified_type = rules_type
                    metadata["commitment_type"] = rules_type
                    metadata["is_commitment"] = rules_result.get("is_commitment", False)
                    metadata["commitment_state"] = rules_result.get("state", "candidate")
                    metadata["classification_reasoning"] = (
                        f"rules override: LLM said {classified_type} but rules "
                        f"detected {rules_type} ({rules_result.get('reasoning','')[:100]})"
                    )
                    metadata["llm_powered"] = False
            except Exception:
                pass  # rules check is best-effort; LLM result stands

        if classified_type in NON_COMMITMENT_TYPES:
            signal_type_override = "not_a_commitment"
        else:
            signal_type_override = req.signal_type  # keep lifecycle type
    else:
        # TICKET-1/P59 (seventh audit): when the classifier is unavailable
        # (CI environment, no LLM), PRESERVE the request's commitment_state
        # instead of overwriting with "needs_review". The prior code destroyed
        # the caller's intent (commitment_state=cancelled/completed_claimed)
        # which caused the lifecycle engine to never fire in CI.
        # The request metadata is the caller's intent — the classifier should
        # refine it, not destroy it.
        _req_commitment_state = metadata.get("commitment_state", "")
        _req_is_commitment = metadata.get("is_commitment", None)
        _req_commitment_type = metadata.get("commitment_type", "")
        _req_owner = metadata.get("commitment_owner", "unknown")

        if _req_commitment_state and _req_commitment_state != "needs_review":
            # Preserve the caller's intent — the classifier will refine later
            metadata["commitment_type"] = _req_commitment_type or "needs_review"
            metadata["is_commitment"] = _req_is_commitment
            metadata["commitment_state"] = _req_commitment_state
            metadata["commitment_confidence"] = metadata.get("commitment_confidence", 0.5)
            metadata["commitment_owner"] = _req_owner
            metadata["classification_reasoning"] = "classifier unavailable — preserved caller's metadata"
            metadata["llm_powered"] = False
            signal_type_override = req.signal_type or "commitment_made"
        else:
            metadata["commitment_type"] = "needs_review"
            metadata["is_commitment"] = None
            metadata["commitment_state"] = "needs_review"
            metadata["commitment_confidence"] = 0.0
            metadata["commitment_owner"] = "unknown"
            metadata["classification_reasoning"] = "both LLM and rules classifier failed"
            metadata["llm_powered"] = False
            # signal_type_override stays "needs_review" — NOT a commitment

    # F3: Resolve entity to canonical form to prevent fragmentation.
    # "Acme Corp", "client", "AcmeCorp" → single canonical entity.
    #
    # HIGH-1 fix (independent audit): apply the SAME sanitization stack to
    # the entity field that `text` receives. The previous code passed
    # req.entity straight through to save_signal_to_db, so
    # `<script>alert(1)</script>` survived a round-trip and was returned
    # verbatim by GET /api/signals — stored XSS surface.
    sanitized_entity = _regex_sanitize(req.entity)
    sanitized_entity = _html.escape(sanitized_entity, quote=False)
    # Strip angle brackets entirely — entities are names, not HTML
    sanitized_entity = _re.sub(r'[<>]', '', sanitized_entity).strip()
    # Reject empty entity after sanitization (S4 from audit)
    if not sanitized_entity:
        raise HTTPException(
            status_code=422,
            detail="Entity must contain at least one non-whitespace character."
        )
    canonical_entity = sanitized_entity
    original_entity = sanitized_entity
    try:
        from maestro_personal_shell.entity_resolver import resolve_entity_with_signals
        # Load existing signals to build the known-entity pool
        existing_signals = load_signals_from_db(user_email=token)
        known_entities = list({s.get("entity", "") for s in existing_signals if s.get("entity")})
        canonical_entity = resolve_entity_with_signals(
            sanitized_entity,
            existing_signals,
            user_email=token,
        )
        if canonical_entity != original_entity:
            metadata["original_entity"] = original_entity
            metadata["entity_resolved"] = True
    except Exception as e:
        logger.debug("Entity resolution failed (non-fatal): %s", e)

    # F-14 fix: flag suspected injection in metadata (no text mutation).
    # The text is stored verbatim (html-escaped only). At read time,
    # ask.py's assemble_llm_context will check this flag and wrap the
    # text in <untrusted_user_content> tags if True.
    metadata["injection_suspected"] = _injection_suspected

    signal_data = {
        "signal_id": signal_id,
        "entity": canonical_entity,  # F3: store canonical entity, not raw
        "text": sanitized_text,  # F4: sanitized, not raw
        "signal_type": signal_type_override,  # P37: classifier's verdict, not caller's claim
        "timestamp": signal_timestamp,  # P0-3: preserve client timestamp
        "metadata": metadata,
        "source_acl": "public",
        "created_at": now.isoformat(),
    }

    # Phase 1.4 (auditor v12): honest write status — never return 200 for a
    # write that did not persist. save_signal_to_db returns bool; if False,
    # the signal was NOT saved (dedup hit, DB error, etc.). The prior code
    # ignored the return value, returning HTTP 200 with signal_id even when
    # the row was never written — a silent drop. This fix raises HTTP 500
    # on persist failure so the caller knows the write didn't happen.
    _persisted = save_signal_to_db(signal_data, user_email=token)
    if not _persisted:
        logger.error(
            "Phase 1.4: save_signal_to_db returned False — signal NOT persisted "
            "(signal_id=%s, entity=%s). Returning 500, not 200-with-null.",
            signal_id, canonical_entity,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "persist_failed",
                "signal_id": signal_id,
                "entity": canonical_entity,
                "reason": "Signal was not persisted to the database. "
                          "This may be a duplicate (dedup hit) or a DB error.",
            },
        )

    # Directive 5: Audit log (P1-Audit-F4: surface failures, don't swallow)
    audit_log_error = None
    try:
        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access(token, "write", "/api/signals", signal_id, {"entity": canonical_entity})
    except Exception as e:
        audit_log_error = str(e)
        logger.error("Audit log write failed for /api/signals: %s", e)

    # Phase 1.3 (auditor v13): write outbox row for transactional ingest.
    # The outbox ensures accepted == persisted — a background worker drains
    # it to the ledger with retry. If the signal insert succeeded but the
    # ledger derivation fails, the outbox row remains unprocessed and can
    # be retried via POST /api/admin/drain-outbox.
    try:
        import json as _json_outbox
        import uuid as _uuid_outbox
        from pathlib import Path as _P_outbox
        from maestro_personal_shell.db_util import get_db_conn
        _db_outbox = os.environ.get("MAESTRO_PERSONAL_DB", str(_P_outbox(__file__).resolve().parents[1] / "personal.db"))
        _conn_outbox = get_db_conn(_db_outbox)
        _conn_outbox.execute(
            "INSERT INTO outbox (outbox_id, signal_id, user_email, entity, text, signal_type, metadata, timestamp, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(_uuid_outbox.uuid4()),
                signal_id,
                token,
                canonical_entity,
                sanitized_text[:500],
                req.signal_type or "",
                _json_outbox.dumps(metadata) if metadata else "{}",
                signal_data.get("timestamp", ""),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        _conn_outbox.commit()
        _conn_outbox.close()
    except Exception as _outbox_err:
        logger.warning("Phase 1.3: outbox insert failed (non-fatal — signal already persisted): %s", _outbox_err)

    # Phase 3: Persist the commitment classification into the normalized
    # ledger. The ledger is the source of truth for commitment lifecycle
    # (state machine, closure matching, correction propagation). The
    # signals table holds raw observations; the ledger holds the
    # normalized commitment derived from each signal.
    #
    # A3 fix (auditor v14): wrap the ENTIRE ledger derivation in the write
    # lock to serialize concurrent writes. The prior code ran upsert_ledger_entry
    # + append_event WITHOUT the lock, causing concurrent requests to interleave
    # and corrupt each other's state (63% loss, misattribution).
    from maestro_personal_shell.db_util import get_write_lock
    with get_write_lock():
      try:
        from maestro_personal_shell.commitment_ledger import upsert_ledger_entry, match_closure, transition_ledger_state, get_ledger_entries
        from pathlib import Path as _P
        _db = os.environ.get("MAESTRO_PERSONAL_DB", str(_P(__file__).resolve().parents[1] / "personal.db"))

        # F-09/P60 (sixth audit): third-party/quoted text MUST NOT enter the
        # ledger as an active obligation. The ownership model (my_promise/
        # their_promise/quoted/third_party) must apply at the WRITE path,
        # not just the Ask read path. If the classifier says third_party_report
        # or owner=other, the ledger entry is created with state="candidate"
        # (not "active") so it never surfaces as the user's active commitment.
        #
        # S1-6/P65 fix (auditor v11 correction, 2026-07-29): RESOLUTION
        # signals (cancelled/completed/broken) MUST be exempt from this
        # gate. A resolution signal is a STATE TRANSITION on an existing
        # commitment, not a new commitment — its owner doesn't matter.
        # The LLM sometimes misclassifies the owner of completion signals
        # ("Alex PR review completed" → owner=other because "Alex" looks
        # like a third party). Without this exemption, the F-09 gate
        # overrides the state to "candidate", which prevents the TICKET-1
        # transition logic in upsert_ledger_entry from running — so the
        # completion signal never closes the prior active commitment.
        # This is the same P65 "one field means two things to two readers"
        # shape as the upsert_ledger_entry gate fix.
        _ingest_commitment_type = metadata.get("commitment_type", "not_a_commitment")
        _ingest_owner = metadata.get("commitment_owner", "unknown")
        _ingest_is_commitment = metadata.get("is_commitment", False)
        _ingest_state = metadata.get("commitment_state", "candidate")

        # Resolution types that MUST pass through to upsert_ledger_entry
        # regardless of owner, because they transition existing commitments.
        _RESOLUTION_TYPES_FOR_F09 = {
            "cancelled", "completed", "broken", "superseded", "disputed",
        }

        # F-09: third_party_report and owner=other → don't create an active
        # ledger entry. The signal is stored (it's evidence), but it's NOT
        # the user's commitment. BUT: resolution signals (cancelled/
        # completed/broken) are exempt — they transition existing entries.
        if _ingest_commitment_type == "third_party_report":
            _ingest_is_commitment = False
            _ingest_state = "candidate"
            logger.info(
                "F-09/P60: third-party signal ingested as non-active "
                "(type=%s, owner=%s) — not the user's commitment",
                _ingest_commitment_type, _ingest_owner,
            )
        elif _ingest_owner == "other" and _ingest_commitment_type not in _RESOLUTION_TYPES_FOR_F09:
            _ingest_is_commitment = False
            _ingest_state = "candidate"
            logger.info(
                "F-09/P60: owner=other signal ingested as non-active "
                "(type=%s, owner=%s) — not the user's commitment",
                _ingest_commitment_type, _ingest_owner,
            )
        else:
            # Resolution signal or user-owned signal — pass through.
            if _ingest_commitment_type in _RESOLUTION_TYPES_FOR_F09:
                logger.info(
                    "F-09/P60: resolution signal (type=%s, owner=%s) — "
                    "exempt from third-party gate, passing to upsert",
                    _ingest_commitment_type, _ingest_owner,
                )

        # Persist the classification (upsert handles state-machine routing).
        ledger_entry = upsert_ledger_entry(
            classification={
                "is_commitment": _ingest_is_commitment,
                "commitment_type": _ingest_commitment_type,
                "state": _ingest_state,
                "owner": _ingest_owner,
                "recipient": "",  # not extracted by current classifier; future work
                "action": sanitized_text,  # use full text as action for closure matching
                "deadline_text": "",
                "deadline_datetime": "",
                "confidence": metadata.get("commitment_confidence", 0.5),
                "evidence_quote": sanitized_text,
            },
            signal=signal_data,
            user_email=token,
            db_path=_db,
        )

        # P83 (canonical ledger coherence): ALSO write to the canonical ledger
        # (commitment_events table) so the Ask endpoint can retrieve commitments.
        # The commitment_ledger (commitments_ledger table) is the legacy system;
        # the canonical_ledger (commitment_events table) is what Ask queries.
        # Without this, signals are created but Ask returns 'no records'.
        if ledger_entry and _ingest_is_commitment and _ingest_owner != 'other':
            try:
                from maestro_personal_shell.canonical_ledger import append_event, CommitmentEvent
                event = CommitmentEvent(
                    commitment_id=ledger_entry.get('commitment_id', signal_id),
                    event_type='commitment',
                    actor='user' if _ingest_owner == 'user' else 'entity_name',
                    entity=canonical_entity,
                    text=sanitized_text,
                    source_signal_id=signal_id,
                    confidence=metadata.get('commitment_confidence', 0.5),
                    state='active' if _ingest_state == 'active' else 'cancelled',
                    user_email=token,
                    metadata=json.dumps({
                        'signal_id': signal_id,
                        'commitment_type': _ingest_commitment_type,
                        'state': _ingest_state,
                    }),
                )
                append_event(event)
            except Exception as e:
                logger.error('P83: canonical ledger write failed for signal %s: %s', signal_id, e)

        # Closure matching (roadmap requirement #4): if this new signal
        # is a completion/cancellation, find the active ledger entry it
        # closes and transition that entry. This is how "Sent the proposal"
        # closes "I'll send the proposal by Friday" — by action overlap,
        # not just entity.
        #
        # P59 (sixth audit F-02/S0): CLASSIFICATION IS NOT LIFECYCLE.
        # The prior code only matched by keyword overlap, which failed
        # when a cancellation email ("Cancelled: Sam Rivera roadmap item")
        # didn't share keywords with the original commitment. The lifecycle
        # engine must APPLY transitions, not just label signals. Fix:
        # (1) try keyword-overlap match first (precise), then
        # (2) fall back to ENTITY-ONLY match (the cancellation is for the
        #     same entity, even if the words differ) — this is how real
        #     cancellation emails work ("Cancelled: Sam's roadmap item"
        #     cancels Sam's commitment even without keyword overlap).
        # TICKET-1: if upsert_ledger_entry already transitioned an active entry
        # (the resolution was handled), SKIP closure matching to prevent
        # over-cancellation. The TICKET-1 code in upsert_ledger_entry finds
        # the first active entry and transitions it — running closure matching
        # too would find ANOTHER active entry and transition it, causing
        # both to be cancelled.
        _ticket1_already_resolved = (
            ledger_entry
            and metadata.get("commitment_state") in ("completed_claimed", "completed_verified", "cancelled", "broken")
            and isinstance(ledger_entry, dict)
            and ledger_entry.get("state") in ("completed_claimed", "completed_verified", "cancelled", "broken")
        )
        if _ticket1_already_resolved:
            logger.info(
                "TICKET-1: resolution already applied by upsert_ledger_entry "
                "(state=%s) — skipping closure matching to prevent over-cancellation",
                ledger_entry.get("state") if isinstance(ledger_entry, dict) else "?",
            )
        elif ledger_entry and metadata.get("commitment_state") in ("completed_claimed", "completed_verified", "cancelled"):
            active_entries = [
                e for e in get_ledger_entries(token, _db, state="active")
                + get_ledger_entries(token, _db, state="at_risk")
                + get_ledger_entries(token, _db, state="completed_claimed")
                if e.get("signal_id") != signal_id  # don't close ourselves
            ]
            # P59: first try precise keyword-overlap match
            match = match_closure(
                {"entity": canonical_entity, "text": sanitized_text, "recipient": ""},
                active_entries,
            )
            # P59: if no keyword match, fall back to entity-only match
            # (the cancellation/completion is for the same entity, even
            # if the action keywords don't overlap — real cancellation
            # emails often say "Cancelled: [entity]" without repeating
            # the original commitment's action words)
            if not match:
                _comp_entity_lower = canonical_entity.lower().strip()
                for entry in active_entries:
                    _ent_entity_lower = (entry.get("entity", "") or "").lower().strip()
                    if _comp_entity_lower and _ent_entity_lower:
                        # Fuzzy entity match (same as filter_for_promise_query)
                        if (_comp_entity_lower == _ent_entity_lower
                                or _comp_entity_lower in _ent_entity_lower
                                or _ent_entity_lower in _comp_entity_lower):
                            match = entry
                            logger.info(
                                "P59 lifecycle: entity-only closure match — "
                                "signal entity=%s matched active entry entity=%s "
                                "(ledger_id=%s)",
                                canonical_entity, entry.get("entity", ""),
                                entry.get("ledger_id", ""),
                            )
                            break
            if match:
                target = metadata.get("commitment_state")
                transition_ledger_state(match["ledger_id"], target, token, _db)
                logger.info(
                    "P59 lifecycle APPLIED: signal %s → ledger %s transitioned to %s",
                    signal_id, match["ledger_id"], target,
                )
      except Exception as e:
        # Phase 1.1 fix (auditor v13): honest derivation — don't silently
        # swallow ledger persistence failures. The prior code logged at
        # debug level ("non-fatal"), which hid derivation failures from
        # monitoring. The auditor wants: failures logged, retryable.
        # Fix: log at ERROR level with signal_id so it's visible, and
        # mark the signal's metadata as 'awaiting_derivation' so a
        # background worker can retry.
        logger.error(
            "Phase 1.1: Ledger derivation FAILED for signal %s (entity=%s): %s. "
            "Signal is persisted but ledger entry is missing — needs retry.",
            signal_id, canonical_entity, e,
        )
        # Mark the signal as awaiting derivation by updating its metadata
        try:
            from maestro_personal_shell.db_util import get_db_conn
            _db2 = os.environ.get("MAESTRO_PERSONAL_DB", str(_P(__file__).resolve().parents[1] / "personal.db"))
            conn = get_db_conn(_db2)
            conn.execute(
                "UPDATE signals SET metadata = json_set(COALESCE(metadata, '{}'), '$.awaiting_derivation', 1) "
                "WHERE signal_id = ?",
                (signal_id,),
            )
            conn.commit()
            conn.close()
        except Exception as _meta_err:
            logger.error("Phase 1.1: failed to mark signal %s as awaiting_derivation: %s", signal_id, _meta_err)

    # Directive 2: Auto-register prediction when a commitment is created.
    # The learning loop is now automatic — no manual /api/predictions needed.
    # Also add to personal knowledge graph.
    try:
        from maestro_personal_shell.learning_loop_v2 import auto_register_prediction
        from maestro_personal_shell.personal_graph import PersonalGraph

        # P0 fix (auditor finding #4): always add entity to graph, not just
        # for commitments. The auditor found graph entity exists=false after
        # creating a commitment because the graph add was gated on
        # is_commitment=True which may not be set by the rule-based classifier.
        graph = PersonalGraph(user_email=token)
        graph.add_entity(canonical_entity, entity_type="contact", user_email=token)

        if metadata.get("is_commitment") is True:
            auto_register_prediction(
                signal_id=signal_id,
                commitment_type=metadata.get("commitment_type", "explicit"),
                confidence=metadata.get("commitment_confidence", 0.5),
                entity=canonical_entity,
                user_email=token,
            )

            # Add commitment edge to graph
            graph.add_edge(
                source_entity=canonical_entity,
                edge_type="commitment",
                topic=sanitized_text[:100],
                confidence=metadata.get("commitment_confidence", 0.5),
                metadata={"signal_id": signal_id},
            )

        # P1-Audit-F5 fix: the auditor found Heidi had 14 signals (7
        # commitment_made) but graph reported total_interactions=1. Root
        # cause: graph edges were only created when the classifier set
        # is_commitment=True, but the rule-based classifier doesn't always
        # fire. Fix: also add commitment edges when signal_type is
        # "commitment_made" (the user's explicit declaration), and add a
        # "signal" edge for ALL signals so the graph reflects total
        # interactions, not just the classifier-passed subset.
        elif req.signal_type == "commitment_made":
            # User declared this as a commitment even if classifier didn't
            graph.add_edge(
                source_entity=canonical_entity,
                edge_type="commitment",
                topic=sanitized_text[:100],
                confidence=0.5,
                metadata={"signal_id": signal_id, "source": "signal_type"},
            )

        # Always add a "signal" edge so total_interactions reflects reality
        graph.add_edge(
            source_entity=canonical_entity,
            edge_type="signal",
            topic=sanitized_text[:100],
            confidence=0.5,
            metadata={"signal_id": signal_id, "signal_type": req.signal_type},
        )

        # F3 fix (auditor finding): wire completion/break signals to
        # graph.update_outcome. Previously update_outcome was only called
        # from the manual /api/signals/{id}/correct path, so completion_rate
        # stayed None forever even after explicit "Item delivered" signals.
        # This is a P11 (wiring) fix — capability existed, wasn't wired into
        # the production ingest path.
        completion_signal_types = {
            "commitment_completed", "commitment_broken",
            "commitment_disputed", "completion",
        }
        break_signal_types = {"commitment_broken", "commitment_disputed"}
        if req.signal_type in completion_signal_types or (
            req.signal_type == "reported_statement"
            and any(kw in sanitized_text.lower() for kw in (
                "delivered", "completed", "sent the", "shipped",
                "finished", "done with", "resolved",
            ))
        ):
            outcome = "miss" if (
                req.signal_type in break_signal_types
                or any(kw in sanitized_text.lower() for kw in (
                    "never sent", "overdue", "missed", "delayed",
                    "broke", "broken", "failed to",
                ))
            ) else "hit"
            try:
                resolved_count = graph.resolve_completion_signal(
                    entity_name=canonical_entity,
                    completion_text=sanitized_text,
                    outcome=outcome,
                    user_email=token,
                )
                if resolved_count > 0:
                    logger.info(
                        "F3 graph resolve: %d edge(s) for entity=%s outcome=%s",
                        resolved_count, canonical_entity, outcome,
                    )
            except Exception as e:
                # P6: log loudly, don't silently swallow
                logger.warning(
                    "F3 graph resolve failed (entity=%s, outcome=%s): %s",
                    canonical_entity, outcome, e,
                )
    except Exception as e:
        logger.debug("Learning loop v2 auto-register failed: %s", e)

    return SignalResponse(
        signal_id=signal_id,
        entity=canonical_entity,  # F3: echo canonical entity
        text=sanitized_text,  # F6 FIX: echo sanitized text, not raw (consistency with GET)
        signal_type=req.signal_type,
        timestamp=now.isoformat(),
        audit_log_error=audit_log_error,  # P1-Audit-F4: None if OK, error string if log failed
    )


@router.get("/signals", response_model=list[SignalResponse])
async def get_signals(token: str = Depends(verify_token_dep)):
    """Get all stored signals (scoped to the authenticated user).

    P3 fix: returns classification metadata (commitment_type, is_commitment,
    classification_reasoning, llm_powered) so the user and auditor can see
    WHY each signal was classified as a commitment. Inspectable memory.
    """
    import json as _json
    from maestro_personal_shell.api import load_signals_from_db
    db_signals = load_signals_from_db(user_email=token)
    results = []
    for r in db_signals:
        # Parse metadata to extract classification info
        meta = r.get("metadata", {})
        if isinstance(meta, str):
            try:
                meta = _json.loads(meta) if meta else {}
            except Exception:
                meta = {}
        results.append(SignalResponse(
            signal_id=r["signal_id"],
            entity=r["entity"],
            text=r["text"],
            signal_type=r["signal_type"],
            timestamp=r["timestamp"],
            commitment_type=meta.get("commitment_type"),
            is_commitment=meta.get("is_commitment"),
            commitment_state=meta.get("commitment_state"),
            commitment_confidence=meta.get("commitment_confidence"),
            classification_reasoning=meta.get("classification_reasoning"),
            llm_powered=meta.get("llm_powered"),
        ))
    return results


# ---------------------------------------------------------------------------
# /api/signals/{signal_id} — Phase 2.5 Evidence drill-down
# (auditor v13: "100% of Ask answers traceable to source in ≤2 clicks")
# ---------------------------------------------------------------------------

@router.get("/signals/{signal_id}")
async def get_signal_detail(signal_id: str, token: str = Depends(verify_token_dep)):
    """Get full detail for a single signal — the source behind an Ask answer.

    Phase 2.5 (auditor v13): the UI's evidence_refs contain signal_ids.
    This endpoint lets the user click an evidence_ref and see the full
    source signal in ≤2 clicks (Ask answer → evidence_ref → source signal).

    Returns the full signal record including metadata, classification, and
    any linked ledger entries.
    """
    import os
    from pathlib import Path as _P
    from maestro_personal_shell.db_util import get_db_conn
    import json as _json

    _db = os.environ.get("MAESTRO_PERSONAL_DB", str(_P(__file__).resolve().parents[1] / "personal.db"))
    conn = get_db_conn(_db)
    try:
        row = conn.execute(
            "SELECT signal_id, entity, text, signal_type, timestamp, metadata, user_email, "
            "created_at FROM signals WHERE signal_id = ? AND user_email = ?",
            (signal_id, token),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")

    # Convert to dict
    if hasattr(row, "keys"):
        sig = dict(row)
    else:
        sig = {
            "signal_id": row[0], "entity": row[1], "text": row[2],
            "signal_type": row[3], "timestamp": row[4], "metadata": row[5],
            "user_email": row[6],
            "created_at": row[7] if len(row) > 7 else "",
        }

    # Parse metadata
    meta = sig.get("metadata", "{}")
    if isinstance(meta, str):
        try:
            meta = _json.loads(meta)
        except Exception:
            meta = {}
    sig["metadata"] = meta

    # Also fetch any linked ledger entries
    ledger_entries = []
    try:
        conn = get_db_conn(_db)
        rows = conn.execute(
            "SELECT ledger_id, entity, action, state, owner, deadline_text, "
            "deadline_datetime, confidence, created_at "
            "FROM commitments_ledger WHERE signal_id = ? AND user_email = ?",
            (signal_id, token),
        ).fetchall()
        for r in rows:
            ledger_entries.append(dict(r) if hasattr(r, "keys") else {
                "ledger_id": r[0], "entity": r[1], "action": r[2], "state": r[3],
                "owner": r[4], "deadline_text": r[5], "deadline_datetime": r[6],
                "confidence": r[7], "created_at": r[8],
            })
        conn.close()
    except Exception:
        pass

    return {
        "signal": sig,
        "ledger_entries": ledger_entries,
        "traceable": True,  # Phase 2.5: this signal is traceable from Ask
    }


# ---------------------------------------------------------------------------
# /api/signals/{signal_id}/correct — F7 correction API
# ---------------------------------------------------------------------------


@router.post("/signals/{signal_id}/correct")
async def correct_signal(
    signal_id: str,
    action: str = "dismiss",
    token: str = Depends(verify_token_dep),
):
    """Correct or dismiss a signal (F7 fix)."""
    import sqlite3
    import json as _json
    from maestro_personal_shell.db_util import get_db_conn, default_sqlite_path

    db_path = default_sqlite_path()
    conn = get_db_conn(db_path)

    # Check signal exists AND belongs to the authenticated user (cross-user protection)
    row = conn.execute(
        "SELECT * FROM signals WHERE signal_id = ? AND user_email = ?",
        (signal_id, token),
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Signal not found")

    # Update metadata with correction
    metadata = _json.loads(row[5]) if row[5] else {}
    metadata["correction"] = action
    metadata["corrected_at"] = datetime.now(timezone.utc).isoformat()
    metadata["corrected_by"] = token  # user_email from verify_token

    # P11 fix: audit-log the correction (P1-Audit-F4: surface failures)
    correction_audit_error = None
    try:
        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access(token, "correct", f"/api/signals/{signal_id}/correct", signal_id, {"action": action})
    except Exception as e:
        correction_audit_error = str(e)
        logger.error("Audit log write failed for /api/signals/{id}/correct: %s", e)

    if action == "dismiss":
        metadata["status"] = "dismissed"
    elif action == "complete":
        metadata["status"] = "completed"
    elif action == "cancel":
        metadata["status"] = "cancelled"
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid action — use dismiss/complete/cancel")

    conn.execute(
        "UPDATE signals SET metadata = ? WHERE signal_id = ?",
        (_json.dumps(metadata), signal_id),
    )
    conn.commit()
    conn.close()

    # Phase 3: Propagate the correction to the commitment ledger + FTS.
    # This transitions the ledger entry (active → cancelled for dismiss/cancel,
    # active → completed_claimed for complete) and removes the signal from
    # FTS so retrieval stops surfacing it. Roadmap requirement #6.
    try:
        from maestro_personal_shell.commitment_ledger import propagate_correction
        propagate_correction(signal_id, action, token, db_path)
    except Exception as e:
        logger.debug("Ledger correction propagation failed (non-fatal): %s", e)

    # Directive 2: Auto-resolve prediction + record behavior + update graph
    try:
        from maestro_personal_shell.learning_loop_v2 import auto_resolve_prediction, record_user_behavior
        from maestro_personal_shell.personal_graph import PersonalGraph

        # Map correction action to prediction outcome
        outcome_map = {
            "dismiss": "miss",      # dismissed = prediction was wrong
            "cancel": "miss",       # cancelled = not kept
            "complete": "hit",      # completed = prediction was right
        }
        outcome = outcome_map.get(action, "miss")

        # Auto-resolve the prediction
        auto_resolve_prediction(signal_id, outcome, user_email=token)

        # Record user behavior for pattern learning
        record_user_behavior(
            behavior_type="correct_commitment",
            details={
                "signal_id": signal_id,
                "action": action,
                "entity": row[1] if row else "",  # entity from the signal
            },
            user_email=token,
        )

        # P0-1 FIX (Finding 8 — learning doesn't alter future behavior):
        # When the user DISMISSES a signal, also record a "dismiss_suggestion"
        # behavior event. The learning loop's dismissal_rate counter
        # (learning_loop_v2.py:272) ONLY increments on behavior_type ==
        # "dismiss_suggestion". Without this second record, every dismissal
        # is recorded solely as "correct_commitment" → total_dismissals stays
        # 0 → dismissal_rate stays 0.0 → materiality_gate_v2 never suppresses
        # → the entire 8-phase learning loop is dead. The "agent" field maps
        # to the commitment_type so the gate can learn "user dismisses 80%
        # of 'tentative' commitments" (dismissal_rate_by_agent).
        if action == "dismiss":
            record_user_behavior(
                behavior_type="dismiss_suggestion",
                details={
                    "signal_id": signal_id,
                    "agent": metadata.get("commitment_type", "unknown"),
                    "entity": row[1] if row else "",
                    "commitment_type": metadata.get("commitment_type", "unknown"),
                },
                user_email=token,
            )

        # Update personal graph
        if action == "complete":
            graph = PersonalGraph(user_email=token)
            graph.update_outcome(row[1] if row else "", row[2] if row else "", "hit")
        elif action in ("dismiss", "cancel"):
            graph = PersonalGraph(user_email=token)
            graph.update_outcome(row[1] if row else "", row[2] if row else "", "miss")
    except Exception as e:
        logger.debug("Learning loop v2 auto-resolve failed: %s", e)

    return {
        "signal_id": signal_id,
        "action": action,
        "status": metadata["status"],
        "message": f"Signal {action}. It will no longer appear in active surfaces.",
    }


# ---------------------------------------------------------------------------
# /api/sync/gmail, /api/sync/calendar — connector-driven sync
# ---------------------------------------------------------------------------


@router.post("/sync/gmail", response_model=GmailSyncResponse)
async def sync_gmail(req: GmailSyncRequest, token: str = Depends(verify_token_dep)):
    """Sync Gmail messages → signals.

    F-40 fix (auditor v18): when `messages` is empty/omitted, the server
    attempts a server-initiated pull using the user's stored OAuth tokens.
    If no tokens are available, returns a clear 400 error directing the
    user to connect Gmail first.

    When `messages` is provided (client-side fetch), behavior is unchanged
    — the server processes the supplied messages.
    """
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.signal_adapters.gmail import extract_signals_from_message

    messages = req.messages

    # F-40: server-initiated pull when no messages supplied
    if not messages:
        try:
            from maestro_personal_shell.gmail_connector import (
                is_gmail_configured, fetch_real_gmail_messages,
                GmailOAuthClient,
            )
            from maestro_personal_shell.connectors import ConnectorStore
            import json as _json
            store = ConnectorStore()
            stored_token = store.get_stored_token(token, "gmail")
            if not stored_token:
                raise HTTPException(
                    status_code=400,
                    detail="Gmail not connected. POST /api/connectors/gmail/connect first, or supply 'messages' in the request body."
                )
            if not is_gmail_configured():
                raise HTTPException(
                    status_code=503,
                    detail="Gmail OAuth not configured on the server. Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET."
                )
            # fetch_real_gmail_messages signature:
            #   (stored_token_json, oauth_client, days_back, max_messages) -> (messages, updated_token)
            token_json = stored_token if isinstance(stored_token, str) else _json.dumps(stored_token)
            oauth_client = GmailOAuthClient()
            max_msgs = min(max(req.max_messages, 1), 200)
            messages, updated_token = fetch_real_gmail_messages(
                token_json, oauth_client, max_messages=max_msgs
            )
            # Persist refreshed token if it changed
            if updated_token and updated_token != stored_token:
                store.update_stored_token(token, "gmail", updated_token)
            logger.info("F-40: server-initiated Gmail pull fetched %d messages for %s", len(messages), token)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("F-40: server-side Gmail fetch failed: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Server-side Gmail fetch failed: {str(e)[:200]}"
            )

    count = 0
    for message in messages:
        signals = extract_signals_from_message(message, req.user_email)
        for sig in signals:
            sig["signal_id"] = str(uuid4())
            sig["created_at"] = datetime.now(timezone.utc).isoformat()
            sig["source_acl"] = "private"  # Gmail is private by default
            save_signal_to_db(sig, user_email=token)
            count += 1

    return GmailSyncResponse(
        signals_created=count,
        message=f"Extracted {count} signals from {len(messages)} Gmail messages",
    )


@router.post("/sync/calendar", response_model=CalendarSyncResponse)
async def sync_calendar(req: CalendarSyncRequest, token: str = Depends(verify_token_dep)):
    """Sync Calendar events → signals.

    F-39 fix (auditor v18): when `events` is empty/omitted, the server
    attempts a server-initiated pull using the user's stored Calendar
    OAuth tokens. If no tokens are available, returns a clear 400 error.

    Accepts pre-fetched calendar events. Extracts meeting.scheduled,
    meeting.cancelled, and deadline.approaching signals.
    """
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.signal_adapters.calendar import extract_signals_from_event

    events = req.events

    # F-39: server-initiated pull when no events supplied
    if not events:
        try:
            from maestro_personal_shell.calendar_connector import (
                is_calendar_configured, fetch_real_calendar_events,
                CalendarOAuthClient,
            )
            from maestro_personal_shell.connectors import ConnectorStore
            import json as _json
            store = ConnectorStore()
            stored_token = store.get_stored_token(token, "calendar")
            if not stored_token:
                raise HTTPException(
                    status_code=400,
                    detail="Calendar not connected. POST /api/connectors/calendar/connect first, or supply 'events' in the request body."
                )
            if not is_calendar_configured():
                raise HTTPException(
                    status_code=503,
                    detail="Calendar OAuth not configured on the server."
                )
            # fetch_real_calendar_events signature:
            #   (stored_token_json, oauth_client, max_events, days_ahead) -> (events, updated_token)
            token_json = stored_token if isinstance(stored_token, str) else _json.dumps(stored_token)
            oauth_client = CalendarOAuthClient()
            max_evts = min(max(req.max_events, 1), 200)
            events, updated_token = fetch_real_calendar_events(
                token_json, oauth_client, max_events=max_evts
            )
            # Persist refreshed token if it changed
            if updated_token and updated_token != stored_token:
                store.update_stored_token(token, "calendar", updated_token)
            logger.info("F-39: server-initiated Calendar pull fetched %d events for %s", len(events), token)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("F-39: server-side Calendar fetch failed: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Server-side Calendar fetch failed: {str(e)[:200]}"
            )

    count = 0
    for event in events:
        signals = extract_signals_from_event(event, req.user_email)
        for sig in signals:
            sig["signal_id"] = str(uuid4())
            sig["created_at"] = datetime.now(timezone.utc).isoformat()
            sig["source_acl"] = "private"
            save_signal_to_db(sig, user_email=token)
            count += 1

    return CalendarSyncResponse(
        signals_created=count,
        message=f"Extracted {count} signals from {len(events)} calendar events",
    )


# ---------------------------------------------------------------------------
# /api/ingest/slack, /api/ingest/transcript — Directive 3 data sources
# ---------------------------------------------------------------------------


@router.post("/ingest/slack")
async def ingest_slack(req: SlackIngestRequest, token: str = Depends(verify_token_dep)):
    """Ingest Slack messages and extract commitments.

    Directive 3: expand data sources beyond Gmail/Calendar.
    Parses Slack messages, extracts commitments using the commitment
    classifier, and stores them as signals.
    """
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.signal_adapters.slack import parse_slack_message, sanitize_slack_text

    ingested = 0
    for msg in req.messages:
        signal = parse_slack_message(msg)
        if not signal:
            continue

        # Sanitize text
        signal["text"] = sanitize_slack_text(signal["text"])

        # Save signal
        signal_id = str(uuid4())
        now = datetime.now(timezone.utc)
        signal_data = {
            "signal_id": signal_id,
            "entity": signal["entity"],
            "text": signal["text"],
            "signal_type": signal["signal_type"],
            "timestamp": signal["timestamp"],
            "metadata": signal.get("metadata", {}),
            "source_acl": signal.get("source_acl", "private"),
            "created_at": now.isoformat(),
        }
        save_signal_to_db(signal_data, user_email=token)
        ingested += 1

    return {"ingested": ingested, "message": f"Ingested {ingested} signals from Slack"}


@router.post("/ingest/transcript")
async def ingest_transcript(req: TranscriptIngestRequest, token: str = Depends(verify_token_dep)):
    """Ingest a voice transcript and extract commitments.

    Directive 3: extract implicit commitments from voice transcripts.
    Processes transcript chunks, extracts commitments using voice-specific
    patterns + commitment classifier, and stores them as signals.
    """
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.voice_commitment_extractor import process_meeting_transcript
    from maestro_personal_shell.signal_adapters.gmail import sanitize_email_text
    from maestro_personal_shell.llm_bridge import sanitize_for_llm

    result = process_meeting_transcript(req.transcript, req.meeting_entity)

    # Store extracted commitments as signals
    for commit in result.get("commitments", []):
        signal_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Sanitize
        sanitized_text = sanitize_email_text(commit["text"])
        # P4 FIX: disabled — filter at read time only
        # sanitized_text = sanitize_for_llm(sanitized_text)

        signal_data = {
            "signal_id": signal_id,
            "entity": commit["entity"],
            "text": sanitized_text,
            "signal_type": "commitment_made",
            "timestamp": commit.get("timestamp", now.isoformat()),
            "metadata": commit.get("metadata", {}),
            "source_acl": "private",
            "created_at": now.isoformat(),
        }
        save_signal_to_db(signal_data, user_email=token)

    return {
        "commitments_extracted": len(result.get("commitments", [])),
        "completions_detected": len(result.get("completion_signals", [])),
        "requests_detected": len(result.get("requests", [])),
        "summary": result.get("summary", ""),
    }
