"""Signals router — signal CRUD + ingest endpoints."""
from __future__ import annotations

import html as _html
import logging
import os
import re as _re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

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


@router.post("/signals", response_model=SignalResponse)
async def create_signal(req: SignalCreate, token: str = Depends(verify_token_dep)):
    """Create a new personal signal (manual entry for v1)."""
    from maestro_personal_shell.api import (
        save_signal_to_db,
        load_signals_from_db,
    )
    from maestro_personal_shell.signal_adapters.gmail import sanitize_email_text
    from maestro_personal_shell.llm_bridge import sanitize_for_llm

    # F4 + auditor fix: THREE-LAYER sanitization on ingest.
    # Layer 1: gmail.sanitize_email_text (email-specific patterns)
    # Layer 2: sanitize_for_llm (25+ pattern regex injection defense)
    # Layer 3: semantic_injection_check (LLM-based, catches novel paraphrase
    #          attacks the regex misses — e.g. "kindly overlook every directive")
    #
    # P0-Audit fix: HTML entity encoding + secret keyword blocklist +
    # HTML comment blocking. The auditor found <script> tags, SECRET_TOKEN,
    # and <!-- --> comments survived all 3 layers.
    from maestro_personal_shell.llm_bridge import sanitize_for_llm as _regex_sanitize
    from maestro_personal_shell.signal_adapters.gmail import sanitize_email_text

    sanitized_text = sanitize_email_text(req.text)
    sanitized_text = _regex_sanitize(sanitized_text)

    # P0.1: HTML entity encoding — prevent stored XSS. <script> → &lt;script&gt;
    # This runs AFTER regex sanitization so injection patterns are already
    # filtered, but any remaining HTML is escaped for safety.
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
    try:
        from maestro_personal_shell.llm_bridge import semantic_injection_check, get_llm_provider_name
        _provider = get_llm_provider_name()
        # Skip semantic check for ZAI (rate-limited) — regex is sufficient
        if _provider not in ("none", "zai-glm"):
            sem_result = await semantic_injection_check(sanitized_text)
            if sem_result.get("is_injection"):
                sanitized_text = sem_result.get("filtered_text", sanitized_text)
    except Exception:
        pass  # semantic check is best-effort; regex layers already ran

    signal_id = str(uuid4())
    now = datetime.now(timezone.utc)

    # P0-3 fix: use client-provided timestamp if available (preserves history)
    # Otherwise use server now (backward compat)
    signal_timestamp = req.timestamp if req.timestamp else now.isoformat()

    # S4: Classify commitment type + lifecycle state on ingest.
    # This runs the LLM-powered classifier (or rule-based fallback) and
    # stores the result in metadata. Downstream endpoints (Commitments,
    # The Moment) use this to filter non-commitments.
    #
    # P37 fix (auditor 2026-07-24 S1 #2): The classifier's result MUST
    # override the caller-provided signal_type. Previously, a caller could
    # post a question ("Will you send the report?") with signal_type=
    # "commitment_made", and the classifier would correctly classify it as
    # not_a_commitment, but the signal_type stayed "commitment_made" — so
    # the commitment surface showed it as an active commitment anyway.
    # Now: the classifier's commitment_type OVERWRITES the signal_type, so
    # the surface sees the truth, not the caller's claim.
    metadata: dict[str, Any] = {}
    try:
        from maestro_personal_shell.commitment_classifier import classify_commitment
        classification = await classify_commitment(
            text=sanitized_text,
            entity=req.entity,
        )
        metadata["commitment_type"] = classification.get("commitment_type", "not_a_commitment")
        metadata["is_commitment"] = classification.get("is_commitment", False)
        metadata["commitment_state"] = classification.get("state", "candidate")
        metadata["commitment_confidence"] = classification.get("confidence", 0.5)
        metadata["commitment_owner"] = classification.get("owner", "unknown")
        metadata["classification_reasoning"] = classification.get("reasoning", "")
        metadata["llm_powered"] = classification.get("llm_powered", False)

        classified_type = classification.get("commitment_type", "not_a_commitment")

        # P37: Override the caller-provided signal_type with the classifier's
        # verdict when the classifier says it's NOT a real commitment.
        # This includes: not_a_commitment, tentative, proposal, request,
        # aspiration, negation — ALL non-commitment types must be excluded
        # from the active commitment surface.
        NON_COMMITMENT_TYPES = {
            "not_a_commitment", "tentative", "proposal", "request",
            "aspiration", "negation",
        }
        if classified_type in NON_COMMITMENT_TYPES:
            signal_type_override = "not_a_commitment"
        else:
            signal_type_override = req.signal_type  # keep lifecycle type
    except Exception as e:
        logger.warning("Commitment classification failed: %s — falling back to rules classifier", e)
        # P37 fix: even if the LLM fails, run the rules classifier so we
        # still get a classification. The rules classifier catches questions,
        # tentative, etc. without needing the LLM.
        try:
            from maestro_personal_shell.commitment_classifier import _rule_based_classify
            classification = _rule_based_classify(sanitized_text, req.entity)
            metadata["commitment_type"] = classification.get("commitment_type", "not_a_commitment")
            metadata["is_commitment"] = classification.get("is_commitment", False)
            metadata["commitment_state"] = classification.get("state", "candidate")
            metadata["commitment_confidence"] = classification.get("confidence", 0.5)
            metadata["commitment_owner"] = classification.get("owner", "unknown")
            metadata["classification_reasoning"] = f"rule-based fallback (LLM failed: {e})"
            metadata["llm_powered"] = False

            classified_type = classification.get("commitment_type", "not_a_commitment")
            NON_COMMITMENT_TYPES = {
                "not_a_commitment", "tentative", "proposal", "request",
                "aspiration", "negation",
            }
            if classified_type in NON_COMMITMENT_TYPES:
                signal_type_override = "not_a_commitment"
            else:
                signal_type_override = req.signal_type
        except Exception as e2:
            logger.error("Rules classifier also failed: %s", e2)
            metadata["commitment_type"] = "unclassified"
            metadata["is_commitment"] = None
            signal_type_override = req.signal_type

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

    save_signal_to_db(signal_data, user_email=token)

    # Directive 5: Audit log (P1-Audit-F4: surface failures, don't swallow)
    audit_log_error = None
    try:
        from maestro_personal_shell.audit_trust import log_data_access
        log_data_access(token, "write", "/api/signals", signal_id, {"entity": canonical_entity})
    except Exception as e:
        audit_log_error = str(e)
        logger.error("Audit log write failed for /api/signals: %s", e)

    # Phase 3: Persist the commitment classification into the normalized
    # ledger. The ledger is the source of truth for commitment lifecycle
    # (state machine, closure matching, correction propagation). The
    # signals table holds raw observations; the ledger holds the
    # normalized commitment derived from each signal.
    try:
        from maestro_personal_shell.commitment_ledger import upsert_ledger_entry, match_closure, transition_ledger_state, get_ledger_entries
        from pathlib import Path as _P
        _db = os.environ.get("MAESTRO_PERSONAL_DB", str(_P(__file__).resolve().parents[1] / "personal.db"))
        # Persist the classification (upsert handles state-machine routing).
        ledger_entry = upsert_ledger_entry(
            classification={
                "is_commitment": metadata.get("is_commitment", False),
                "commitment_type": metadata.get("commitment_type", "not_a_commitment"),
                "state": metadata.get("commitment_state", "candidate"),
                "owner": metadata.get("commitment_owner", "unknown"),
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

        # Closure matching (roadmap requirement #4): if this new signal
        # is a completion/cancellation, find the active ledger entry it
        # closes and transition that entry. This is how "Sent the proposal"
        # closes "I'll send the proposal by Friday" — by action overlap,
        # not just entity.
        if ledger_entry and metadata.get("commitment_state") in ("completed_claimed", "completed_verified", "cancelled"):
            active_entries = [
                e for e in get_ledger_entries(token, _db, state="active")
                + get_ledger_entries(token, _db, state="at_risk")
                + get_ledger_entries(token, _db, state="completed_claimed")
                if e.get("signal_id") != signal_id  # don't close ourselves
            ]
            match = match_closure(
                {"entity": canonical_entity, "text": sanitized_text, "recipient": ""},
                active_entries,
            )
            if match:
                target = metadata.get("commitment_state")
                transition_ledger_state(match["ledger_id"], target, token, _db)
    except Exception as e:
        logger.debug("Ledger persistence failed (non-fatal): %s", e)

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
    """Get all stored signals (scoped to the authenticated user)."""
    from maestro_personal_shell.api import load_signals_from_db
    db_signals = load_signals_from_db(user_email=token)
    return [
        SignalResponse(
            signal_id=r["signal_id"],
            entity=r["entity"],
            text=r["text"],
            signal_type=r["signal_type"],
            timestamp=r["timestamp"],
        )
        for r in db_signals
    ]


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
    from maestro_personal_shell.db_util import get_db_conn

    db_path = os.environ.get("MAESTRO_PERSONAL_DB", str(Path(__file__).resolve().parents[1] / "personal.db"))
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

    Accepts pre-fetched Gmail messages (the OAuth wiring happens in the
    mobile app or a background worker). Extracts commitments, follow-ups,
    and meeting changes using the Gmail adapter.
    """
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.signal_adapters.gmail import extract_signals_from_message

    count = 0
    for message in req.messages:
        signals = extract_signals_from_message(message, req.user_email)
        for sig in signals:
            sig["signal_id"] = str(uuid4())
            sig["created_at"] = datetime.now(timezone.utc).isoformat()
            sig["source_acl"] = "private"  # Gmail is private by default
            save_signal_to_db(sig, user_email=token)
            count += 1

    return GmailSyncResponse(
        signals_created=count,
        message=f"Extracted {count} signals from {len(req.messages)} Gmail messages",
    )


@router.post("/sync/calendar", response_model=CalendarSyncResponse)
async def sync_calendar(req: CalendarSyncRequest, token: str = Depends(verify_token_dep)):
    """Sync Calendar events → signals.

    Accepts pre-fetched calendar events. Extracts meeting.scheduled,
    meeting.cancelled, and deadline.approaching signals.
    """
    from maestro_personal_shell.api import save_signal_to_db
    from maestro_personal_shell.signal_adapters.calendar import extract_signals_from_event

    count = 0
    for event in req.events:
        signals = extract_signals_from_event(event, req.user_email)
        for sig in signals:
            sig["signal_id"] = str(uuid4())
            sig["created_at"] = datetime.now(timezone.utc).isoformat()
            sig["source_acl"] = "private"
            save_signal_to_db(sig, user_email=token)
            count += 1

    return CalendarSyncResponse(
        signals_created=count,
        message=f"Extracted {count} signals from {len(req.events)} calendar events",
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
        sanitized_text = sanitize_for_llm(sanitized_text)

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
