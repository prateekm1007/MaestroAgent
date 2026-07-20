"""Commitments router — commitments surface + lifecycle helpers.

Extracted from api.py during the Phase 8 router split. No behavior
changes — same paths, same response schemas, same filters.

This module owns the commitment-filter helpers (_filter_completed_commitments,
_filter_dismissed_commitments, _filter_non_commitments_by_classification,
_filter_corrected_signals, _compute_commitment_confidence, _detect_completion).
api.py re-exports them for backward compatibility with tests that import
them via `from maestro_personal_shell.api import _detect_completion`.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from maestro_personal_shell.models import (
    CommitmentResponse,
    CommitmentsMasterpieceResponse,
    CommitmentSimulationRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/commitments", tags=["commitments"])


# ---------------------------------------------------------------------------
# verify_token lazy proxy (see routers/auth.py for rationale)
# ---------------------------------------------------------------------------


async def verify_token_dep(authorization: str = Header(None)) -> str:
    """Lazy proxy to api.verify_token — decouples this router from api.py's load order."""
    from maestro_personal_shell.api import verify_token
    return await verify_token(authorization=authorization)


# ---------------------------------------------------------------------------
# Filter helpers (used by commitments endpoints AND by other routers —
# api.py re-exports these for backward compatibility with tests)
# ---------------------------------------------------------------------------


def _filter_corrected_signals(signals: list) -> list:
    """Filter out dismissed/completed/cancelled signals (F7 fix)."""
    result = []
    for sig in signals:
        metadata = getattr(sig, "metadata", {}) or {}
        status = metadata.get("status", "") if isinstance(metadata, dict) else ""
        if status in ("dismissed", "completed", "cancelled"):
            continue  # skip corrected signals
        result.append(sig)
    return result


def _filter_dismissed_commitments(commitments: list[dict], signals: list) -> list[dict]:
    """Filter out dismissed commitments by signal_id (auditor fix).

    The auditor found that dismissing a signal didn't remove it from
    Commitments or The Moment. Root cause: _filter_corrected_signals
    was passed to _filter_completed_commitments (which filters by entity
    completion, not by dismissed status).

    This function filters by signal_id: if a commitment's signal_id
    matches a dismissed signal, it's removed.
    """
    # Build set of dismissed signal_ids
    dismissed_ids = set()
    for sig in signals:
        metadata = getattr(sig, "metadata", {}) or {}
        if isinstance(metadata, str):
            try:
                import json as _json
                metadata = _json.loads(metadata)
            except Exception:
                metadata = {}
        status = metadata.get("status", "") if isinstance(metadata, dict) else ""
        correction = metadata.get("correction", "") if isinstance(metadata, dict) else ""
        if status in ("dismissed", "completed", "cancelled") or correction in ("dismiss", "cancel", "complete"):
            sig_id = str(getattr(sig, "signal_id", ""))
            if sig_id:
                dismissed_ids.add(sig_id)

    if not dismissed_ids:
        return commitments

    return [
        c for c in commitments
        if str(c.get("signal_id", "")) not in dismissed_ids
    ]


def _detect_completion(signals: list) -> dict[str, str]:
    """Detect completed commitments from signals.

    F2 fix + auditor fix: completion detection must be:
    1. Signal-specific (not entity-wide) — "Proposal sent" only closes
       the proposal commitment, not ALL commitments for that entity.
    2. Negation-aware — "I never sent" must NOT trigger completion.
    3. Topic-aware — match completion to the original commitment by
       keyword overlap (proposal→proposal, invoice→invoice, etc.)

    Returns dict of signal_id → 'completed' for signals that indicate
    completion of a prior commitment.
    """
    # Negation patterns — if these appear, it's NOT a completion
    negation_patterns = [
        "never sent", "didn't send", "did not send", "haven't sent",
        "has not been sent", "not sent", "not delivered", "not completed",
        "not done", "not finished", "not paid", "not submitted",
        "didn't finish", "did not finish", "didn't complete",
        "won't send", "will not send", "can't send", "cannot send",
        "didn't pay", "did not pay", "haven't paid",
    ]

    completion_keywords = [
        "paid", "sent", "completed", "done", "delivered",
        "finished", "submitted", "approved", "received",
        "closed", "resolved", "fulfilled",
    ]

    completed = {}  # signal_id -> "completed"
    for sig in signals:
        text = str(getattr(sig, "text", "")).lower()
        sig_type = str(getattr(sig, "signal_type", "") or
                      getattr(getattr(sig, "type", ""), "value", "")).lower()

        # P1-Audit-F4 fix: do NOT skip based on signal_type alone. The
        # auditor found that "Taylor confirmed receipt of redlines — closed"
        # was ingested as signal_type="commitment_made" and thus skipped
        # by the old `if "commitment" in sig_type: continue` check. This
        # meant completion signals never triggered the filter. Instead,
        # rely on the keyword check (past-tense "sent", "closed", etc.)
        # and a future-tense guard to avoid matching "I will send".

        # Check for negation — if negated, NOT a completion
        if any(neg in text for neg in negation_patterns):
            continue

        # Future-tense guard: "I will send", "I'll deliver", "going to
        # submit" are commitments, NOT completions. Only past-tense or
        # present-perfect indicates a completed action.
        future_indicators = ["will ", "shall ", "going to ", "i'll ",
                            "plan to ", "intend to ", "promise to "]
        if any(fut in text for fut in future_indicators):
            continue

        # Check if this signal indicates a completion
        if any(kw in text for kw in completion_keywords):
            sig_id = str(getattr(sig, "signal_id", ""))
            completed[sig_id] = "completed"

    return completed


def _detect_cancellation(signals: list) -> dict[str, str]:
    """Detect cancelled commitments from signals (S2-07 fix).

    Cancellation is different from completion:
    - Completion: "sent", "delivered", "done" (the commitment was fulfilled)
    - Cancellation: "never mind", "forget it", "we don't need this" (the
      commitment was withdrawn)

    Both should remove the commitment from the active list, but they have
    different semantics for the ledger (completed vs cancelled state).

    Returns dict of signal_id → 'cancelled' for signals that indicate
    cancellation of a prior commitment.
    """
    cancellation_keywords = [
        "never mind", "forget it", "don't need", "do not need",
        "cancelled", "canceled", "call it off", "called off",
        "no longer needed", "not needed anymore", "scratch that",
        "forget about", "disregard", "ignore that",
        "won't be needed", "will not be needed",
        "pull the plug", "scrap it", "scrap the",
    ]

    # Also check signal_type for explicit cancellation signals
    cancellation_signal_types = {
        "commitment.cancelled", "commitment_canceled",
        "cancellation", "cancelled",
    }

    cancelled = {}  # signal_id -> "cancelled"
    for sig in signals:
        text = str(getattr(sig, "text", "")).lower()
        sig_type = str(getattr(sig, "signal_type", "") or
                      getattr(getattr(sig, "type", ""), "value", "")).lower()

        # Check signal_type first
        if sig_type in cancellation_signal_types:
            sig_id = str(getattr(sig, "signal_id", ""))
            cancelled[sig_id] = "cancelled"
            continue

        # Check keywords
        if any(kw in text for kw in cancellation_keywords):
            sig_id = str(getattr(sig, "signal_id", ""))
            cancelled[sig_id] = "cancelled"

    return cancelled


def _filter_completed_commitments(commitments: list[dict], signals: list) -> list[dict]:
    """Filter out completed AND cancelled commitments (F2 fix + auditor fix + S2-07 fix).

    S2-07 fix: previously, only completion signals (sent, delivered, etc.)
    filtered commitments. Cancellation signals ("never mind", "we don't
    need this", "cancelled") were not handled, so cancelled commitments
    still showed in /api/commitments as active. This caused a canonical
    state inconsistency: What Changed removed the cancelled commitment,
    but /api/commitments still listed it.

    Auditor fix: completion must be signal-specific, not entity-wide.
    "Proposal sent" should only close the proposal commitment for that
    entity, not ALL commitments for that entity.

    Matches completion/cancellation signals to commitments by:
    1. Same entity
    2. Keyword overlap (the completion/cancellation text mentions the commitment topic)
    """
    completed_signal_ids = _detect_completion(signals)

    # S2-07 fix: also detect cancellation signals
    cancelled_signal_ids = _detect_cancellation(signals)

    # Build a map of entity → list of completion signal texts
    entity_completions: dict[str, list[str]] = {}
    for sig in signals:
        sig_id = str(getattr(sig, "signal_id", ""))
        if sig_id in completed_signal_ids:
            entity = str(getattr(sig, "entity", "")).lower()
            text = str(getattr(sig, "text", "")).lower()
            if entity not in entity_completions:
                entity_completions[entity] = []
            entity_completions[entity].append(text)

    # Build a map of entity → list of cancellation signal texts
    entity_cancellations: dict[str, list[str]] = {}
    for sig in signals:
        sig_id = str(getattr(sig, "signal_id", ""))
        if sig_id in cancelled_signal_ids:
            entity = str(getattr(sig, "entity", "")).lower()
            text = str(getattr(sig, "text", "")).lower()
            if entity not in entity_cancellations:
                entity_cancellations[entity] = []
            entity_cancellations[entity].append(text)

    filtered = []
    for c in commitments:
        c_entity = str(c.get("entity", "")).lower()
        c_text = str(c.get("text", "")).lower()

        # S2-07 fix (round 2, auditor Round 7): cancellation must be
        # topic-specific, NOT entity-wide. "Never mind, we don't need the
        # report" should only cancel the report commitment, NOT an unrelated
        # "review the contract" commitment for the same entity.
        #
        # Exception: explicit "cancel everything" phrasing cancels all
        # commitments for that entity.
        if c_entity in entity_cancellations:
            # Check for explicit entity-wide cancellation
            entity_wide_phrases = [
                "cancel everything", "cancel all", "forget everything",
                "scrap everything", "scrap all", "pull the plug on everything",
                "never mind about everything", "forget it all",
                "we don't need anything", "do not need anything",
                "cancel all commitments", "cancel everything with",
            ]
            is_entity_wide = False
            for cancel_text in entity_cancellations[c_entity]:
                if any(phrase in cancel_text for phrase in entity_wide_phrases):
                    is_entity_wide = True
                    break

            if is_entity_wide:
                continue  # entity-wide cancellation — skip ALL commitments

            # Topic-specific cancellation: require keyword overlap between
            # the cancellation text and the commitment text (same logic as
            # completion matching). "Never mind, we don't need the report"
            # has "report" → cancels "I will send the report by Friday"
            # but NOT "I will review the contract by Monday".
            # P2-2026-07-19 fix: strip punctuation before comparing so
            # "report." matches "report" (trailing period was preventing match).
            import re as _re_cancel
            def _normalize_words(text):
                # Remove punctuation, lowercase, split
                cleaned = _re_cancel.sub(r'[^\w\s]', '', text)
                return set(cleaned.split())

            commitment_words = _normalize_words(c_text)
            common_words = {"i", "will", "the", "to", "a", "an", "by", "for",
                            "send", "sent", "is", "are", "was", "were", "be",
                            "have", "has", "that", "this", "it", "in", "on",
                            "at", "of", "and", "or", "but", "not",
                            "never", "mind", "we", "do", "need", "dont",
                            "forget", "cancelled", "canceled", "scratch",
                            "friday", "monday", "tuesday", "wednesday",
                            "thursday", "saturday", "sunday",
                            "tomorrow", "today", "next", "week", "month"}
            commitment_keywords = commitment_words - common_words

            cancelled = False
            for cancel_text in entity_cancellations[c_entity]:
                cancel_words = _normalize_words(cancel_text)
                overlap = commitment_keywords & cancel_words
                if overlap:
                    cancelled = True
                    break

            if cancelled:
                continue  # skip this commitment — it's topic-specifically cancelled

        # Check if there's a completion signal for this entity
        if c_entity in entity_completions:
            # Topic matching: use verb-object pairs, not bag-of-words.
            # The auditor found that "Proposal sent without SSO section"
            # falsely closed the "send the SSO timeline" commitment because
            # "sso" appeared in both. Fix: require POSITIVE mention — if
            # the completion text negates the keyword ("without", "missing",
            # "not"), don't close.
            commitment_words = set(c_text.split())
            common_words = {"i", "will", "the", "to", "a", "an", "by", "for",
                            "send", "sent", "is", "are", "was", "were", "be",
                            "have", "has", "that", "this", "it", "in", "on",
                            "at", "of", "and", "or", "but", "not"}
            commitment_keywords = commitment_words - common_words

            # Negation indicators — if the completion text negates a keyword,
            # it's NOT a completion of that keyword's commitment
            negation_indicators = ["without", "missing", "not", "no ", "lacks",
                                   "doesn't include", "does not include",
                                   "absent", "incomplete", "lacking"]

            closed = False
            for comp_text in entity_completions[c_entity]:
                comp_words = set(comp_text.split())
                overlap = commitment_keywords & comp_words

                if not overlap and commitment_keywords:
                    continue  # no keyword overlap — don't close

                # Check for negation of the overlapping keywords
                # If the completion says "without SSO" or "missing SSO",
                # it's NOT completing the SSO commitment
                has_negation = any(neg in comp_text for neg in negation_indicators)
                if has_negation:
                    # Check if the negation applies to the overlapping keyword
                    for kw in overlap:
                        # If the keyword appears near a negation word, don't close
                        for neg in negation_indicators:
                            if neg in comp_text and kw in comp_text:
                                # Check proximity — if negation and keyword are
                                # within 3 words, it's a negated mention
                                neg_pos = comp_text.find(neg)
                                kw_pos = comp_text.find(kw)
                                if abs(neg_pos - kw_pos) < 30:
                                    closed = False
                                    break
                        else:
                            continue
                        break
                    if not closed:
                        continue

                closed = True
                break

            if closed:
                continue  # skip this commitment — it's completed

        filtered.append(c)

    return filtered


def _filter_non_commitments_by_classification(
    commitments: list[dict],
    signals: list | None = None,
) -> list[dict]:
    """Filter out signals classified as non-commitments (S4 fix).

    Uses the commitment_type stored in signal metadata by the
    commitment_classifier on ingest. Filters out:
    - tentative (hedged, "maybe")
    - proposal (suggestion, not a promise)
    - request (asking, not promising)
    - aspiration ("I hope to")
    - negation (explicit refusal)
    - third_party_report ("he said he will")
    - not_a_commitment

    Keeps:
    - explicit, implicit, conditional (active commitments)
    - unclassified (preserves backward compat when classifier didn't run)
    - None is_commitment (unknown — don't filter)

    The commitments from CommitmentsSurface don't carry metadata, so we
    look up the signal's metadata by signal_id from the signals list.
    """
    NON_COMMITMENT_TYPES = {
        "tentative", "proposal", "request", "aspiration",
        "negation", "third_party_report", "not_a_commitment",
    }

    # Build a lookup of signal_id -> metadata from the signals list
    sig_meta_lookup: dict[str, dict] = {}
    if signals:
        for sig in signals:
            sig_id = getattr(sig, "signal_id", "")
            if not sig_id:
                continue
            meta = getattr(sig, "metadata", {}) or {}
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            sig_meta_lookup[str(sig_id)] = meta if isinstance(meta, dict) else {}

    filtered = []
    for c in commitments:
        sig_id = str(c.get("signal_id", ""))

        # Look up metadata: first from the commitment dict, then from signals
        meta = c.get("metadata", {})
        if not meta and sig_id and sig_id in sig_meta_lookup:
            meta = sig_meta_lookup[sig_id]

        if isinstance(meta, str):
            try:
                import json as _json
                meta = _json.loads(meta)
            except Exception:
                meta = {}

        if not isinstance(meta, dict):
            meta = {}

        ctype = meta.get("commitment_type", "unclassified")
        is_commitment = meta.get("is_commitment", None)

        # If classifier explicitly said "not a commitment", filter it out
        if ctype in NON_COMMITMENT_TYPES:
            continue

        # If is_commitment is explicitly False, filter it out
        if is_commitment is False:
            continue

        # Otherwise keep it (includes unclassified and explicit True)
        filtered.append(c)

    return filtered


def _compute_commitment_confidence(
    commitment: dict,
    calibration_note: str,
    days_stale: int = 0,
) -> float:
    """Compute real per-item confidence for a commitment.

    F5 fix: replaces the flat 0.5/0.0 confidence with a real calculation
    based on:
    - Classification confidence (from commitment_classifier)
    - Calibration history (Brier score)
    - Staleness (older = less confident it'll be kept)
    - Evidence quality (classification type)

    Returns a float 0.0-1.0.
    """
    confidence = 0.5  # base

    # 1. Use classification confidence if available
    meta = commitment.get("metadata", {}) or {}
    if isinstance(meta, str):
        try:
            import json as _json
            meta = _json.loads(meta)
        except Exception:
            meta = {}

    class_conf = meta.get("commitment_confidence")
    if class_conf is not None:
        confidence = float(class_conf)

    # 2. Adjust for staleness — older commitments are less likely to be kept
    if days_stale > 7:
        confidence *= 0.6  # 40% less confident
    elif days_stale > 3:
        confidence *= 0.8  # 20% less confident
    elif days_stale > 1:
        confidence *= 0.9  # 10% less confident

    # 3. Adjust for commitment type — explicit > implicit > conditional
    ctype = meta.get("commitment_type", "unclassified")
    type_adjustments = {
        "explicit": 1.0,      # strong promise
        "implicit": 0.85,     # implied
        "conditional": 0.6,   # depends on condition
        "unclassified": 0.7,  # unknown
    }
    confidence *= type_adjustments.get(ctype, 0.7)

    # 4. If calibration says "insufficient", reduce confidence (be humble)
    if "Insufficient" in calibration_note or "insufficient" in calibration_note:
        confidence *= 0.8  # 20% less confident when uncalibrated

    # 5. If real Brier score exists, adjust based on past accuracy
    # (Brier < 0.25 = well-calibrated, > 0.33 = poor)
    brier_match = re.search(r'Brier[^0-9]*(\d+\.?\d*)', calibration_note)
    if brier_match:
        brier = float(brier_match.group(1))
        if brier < 0.2:
            confidence *= 1.1  # well-calibrated — slightly more confident
        elif brier > 0.35:
            confidence *= 0.7  # poorly calibrated — much less confident

    # Clamp to 0.0-1.0
    return max(0.0, min(1.0, confidence))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CommitmentResponse])
async def get_commitments(as_of: str | None = None, token: str = Depends(verify_token_dep)):
    """Get active commitments — calls Core's commitment classifier via the shell.

    DEPTH: each commitment includes calibration_note (from CalibrationPrimitives)
    and outcome_history (from BehavioralLearningEngine).
    """
    from maestro_personal_shell.api import (
        build_shell,
        _get_real_calibration,
    )

    shell = build_shell(user_email=token, as_of=as_of)
    core = shell.core

    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface
    surface = CommitmentsSurface(shell=shell)
    commitments = surface.get_active_commitments()
    commitments = _filter_completed_commitments(commitments, shell.oem_state.signals)  # F2: filter completed
    commitments = _filter_dismissed_commitments(commitments, shell.oem_state.signals)  # F7: filter dismissed by signal_id
    commitments = _filter_non_commitments_by_classification(commitments, shell.oem_state.signals)  # S4: filter tentative/proposal/request

    # Get stale commitments for at-risk flagging
    # F4 fix (independent audit): use days_threshold=2 to match /the-one.
    # The previous code used the default (5), so /api/commitments showed
    # days_stale=0 for 2-4 day old commitments while /the-one flagged them
    # as stale — temporal inconsistency across surfaces.
    stale = shell.detect_stale_commitments(days_threshold=2)
    stale_map = {}
    for s in stale:
        sig_id = ""
        commit = s.get("commitment", None)
        if commit:
            sig_id = getattr(commit, "signal_id", "") or (commit.get("signal_id", "") if isinstance(commit, dict) else "")
        if sig_id:
            stale_map[sig_id] = s.get("days_stale", 0)

    # DEPTH: get calibration note from Core's calibration_primitives
    cal_note = ""
    if core.calibration_primitives:
        try:
            brier = core.calibration_primitives.brier_score([])
            if brier is None:
                cal_note = _get_real_calibration(user_email=token)
            else:
                cal_note = f"Brier score: {brier:.4f} (lower is better)"
        except Exception:
            cal_note = _get_real_calibration(user_email=token)

    result = []
    for c in commitments:
        sig_id = c.get("signal_id", "")
        days_stale = stale_map.get(sig_id, 0)

        # DEPTH: get outcome history from BehavioralLearningEngine
        outcome = ""
        if core.behavioral_learning_engine:
            try:
                entity = c.get("entity", "")
                metrics = core.behavioral_learning_engine.get_replication_metrics(
                    candidate_id=None
                ) if hasattr(core.behavioral_learning_engine, "get_replication_metrics") else {}
                if metrics and isinstance(metrics, dict):
                    resolved = metrics.get("resolved_count", 0)
                    confirmed = metrics.get("confirmed_count", 0)
                    if resolved > 0:
                        outcome = f"Kept {confirmed}/{resolved} like this"
            except Exception as e:
                logger.debug("outcome failed: %s", e)
        # Coherence fix: also mark as at_risk if there's a broken/overdue
        # reported_statement for the same entity (e.g., Riley's "Never sent")
        entity_lower = c.get("entity", "").lower()
        has_broken_signal = False
        if entity_lower:
            for sig in shell.oem_state.signals:
                if str(getattr(sig, "entity", "")).lower() == entity_lower:
                    sig_text = str(getattr(sig, "text", "")).lower()
                    if any(kw in sig_text for kw in (
                        "never sent", "didn't send", "overdue", "missed",
                        "failed to", "broken", "delayed", "hasn't",
                        "still pending", "not sent", "not delivered",
                    )):
                        has_broken_signal = True
                        break

        result.append(CommitmentResponse(
            entity=c["entity"],
            text=c["text"],
            claim_type=str(c.get("claim_type", "commitment")),
            signal_id=sig_id,
            is_commitment=c.get("is_commitment", True),
            is_at_risk=(sig_id in stale_map) or has_broken_signal,
            days_stale=days_stale,
            deadline=(c.get("metadata", {}) or {}).get("deadline", ""),
            calibration_note=cal_note,
            outcome_history=outcome,
            confidence=_compute_commitment_confidence(c, cal_note, days_stale),
        ))

    return result


@router.get("/the-one", response_model=CommitmentsMasterpieceResponse)
async def get_the_one_commitment(token: str = Depends(verify_token_dep)):
    """The one commitment at risk today — not a list of 47.

    The masterpiece Commitments: returns ONE primary commitment (the
    most at-risk) + the rest as secondary. The inevitability: you know
    what you owe without scrolling.

    Phase 4: reads from the canonical WorldModel so all surfaces agree.
    """
    from maestro_personal_shell.api import build_shell

    shell = build_shell(user_email=token)

    # Phase 4: use the canonical WorldModel instead of independently
    # recomputing filters. This ensures cross-surface coherence.
    from maestro_personal_shell.world_model import build_world_model
    wm = build_world_model(shell=shell, user_email=token)
    commitments = wm.commitments  # canonical: already filtered for completed/dismissed/non-commitment/tombstoned/superseded

    if not commitments:
        return CommitmentsMasterpieceResponse(primary=None, why_primary="", secondary=[])

    # Stale commitments — from the canonical WorldModel (computed once).
    stale_map = {}
    for s in wm.stale_commitments:
        sig_id = ""
        commit = s.get("commitment", None)
        if commit:
            sig_id = getattr(commit, "signal_id", "") or (commit.get("signal_id", "") if isinstance(commit, dict) else "")
        if sig_id:
            stale_map[sig_id] = s.get("days_stale", 0)

    # Build commitment responses with at-risk info
    all_commitments = []
    for c in commitments:
        sig_id = c.get("signal_id", "")
        days_stale = stale_map.get(sig_id, 0)
        all_commitments.append(CommitmentResponse(
            entity=c["entity"],
            text=c["text"],
            claim_type=str(c.get("claim_type", "commitment")),
            signal_id=sig_id,
            is_commitment=c.get("is_commitment", True),
            is_at_risk=sig_id in stale_map,
            days_stale=days_stale,
            deadline=(c.get("metadata", {}) or {}).get("deadline", ""),
        ))

    # The primary is the most at-risk: highest days_stale, then oldest
    def risk_score(c: CommitmentResponse) -> tuple[int, int]:
        return (c.days_stale, -len(c.signal_id))  # stale first, then by ID for stability

    all_commitments.sort(key=risk_score, reverse=True)
    primary = all_commitments[0] if all_commitments else None

    why = ""
    if primary:
        reasons = []
        if primary.is_at_risk:
            reasons.append(f"no follow-up for {primary.days_stale} days")
        if primary.deadline:
            reasons.append(f"deadline: {primary.deadline}")
        if primary.claim_type == "commitment":
            reasons.append("you made this promise")
        why = "; ".join(reasons) if reasons else "most active commitment"

    return CommitmentsMasterpieceResponse(
        primary=primary,
        why_primary=why,
        secondary=all_commitments[1:] if len(all_commitments) > 1 else [],
    )


@router.get("/ledger")
async def get_commitments_ledger(
    state: str | None = None,
    entity: str | None = None,
    limit: int = 100,
    token: str = Depends(verify_token_dep),
):
    """Read the normalized commitments ledger (Phase 3).

    Returns persisted commitment entries with their lifecycle state,
    owner, recipient, action, deadline, and confidence. This is the
    source of truth for commitment lifecycle — the signals table holds
    raw observations; the ledger holds the normalized commitments.

    Filters:
      - state: filter by lifecycle state (candidate/active/at_risk/
        completed_claimed/completed_verified/disputed/cancelled/
        superseded/tombstoned)
      - entity: filter by entity name (exact match)
    """
    import os
    from pathlib import Path as _P
    _db = os.environ.get("MAESTRO_PERSONAL_DB", str(_P(__file__).resolve().parents[1] / "personal.db"))
    from maestro_personal_shell.commitment_ledger import get_ledger_entries
    entries = get_ledger_entries(token, _db, state=state, entity=entity, limit=limit)
    return {"entries": entries, "count": len(entries)}


@router.post("/{ledger_id}/transition")
async def transition_commitment(
    ledger_id: str,
    to_state: str,
    token: str = Depends(verify_token_dep),
):
    """Transition a commitment to a new lifecycle state (Phase 3).

    The transition must be legal per the state machine. Illegal
    transitions are rejected (400) AND audit-logged as
    'rejected_transition'. Legal transitions are applied AND
    audit-logged as 'commitment_transition'.
    """
    import os
    from pathlib import Path as _P
    _db = os.environ.get("MAESTRO_PERSONAL_DB", str(_P(__file__).resolve().parents[1] / "personal.db"))
    from maestro_personal_shell.commitment_ledger import transition_ledger_state, is_legal_transition
    if to_state not in {"candidate", "active", "at_risk", "completed_claimed",
                        "completed_verified", "disputed", "cancelled", "superseded", "tombstoned"}:
        raise HTTPException(status_code=400, detail=f"Unknown state: {to_state}")
    ok = transition_ledger_state(ledger_id, to_state, token, _db)
    if not ok:
        raise HTTPException(status_code=409, detail="Illegal transition or ledger entry not found")
    return {"ledger_id": ledger_id, "state": to_state, "transitioned": True}


@router.post("/simulate")
async def simulate_commitment(
    req: CommitmentSimulationRequest,
    token: str = Depends(verify_token_dep),
):
    """Simulate the impact of taking on a new commitment.

    Directive 4: 'If I take this on, what conflicts with my existing
    commitments?' Analyzes deadline overlaps, entity overload, topic
    conflicts, and priority dilution.
    """
    from maestro_personal_shell.api import build_shell
    from maestro_personal_shell.dynamic_agents import simulate_commitment_impact
    from maestro_personal_shell.surfaces.commitments import CommitmentsSurface

    shell = build_shell(user_email=token)
    surface = CommitmentsSurface(shell=shell)
    existing = surface.get_active_commitments()

    result = simulate_commitment_impact(
        new_commitment_text=req.commitment_text,
        new_entity=req.entity,
        new_deadline=req.deadline,
        existing_commitments=existing,
    )

    return result
