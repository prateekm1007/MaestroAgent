"""
Legacy API Guards — C3 (ACL on derived intelligence) + C7 (tombstone) for
the legacy /api/oem/* routes that the frontend actually calls.

PROBLEM (independent audit, 2026-07-08):
  The C3/C7 fixes at commit 5b38d48 were applied ONLY in the Council bridge
  layer (maestro_cognitive_council/ask_bridge.py). But the frontend calls
  the LEGACY routes 100% of the time:
    - /api/oem/ask/conversation  (12 refs across 6 frontend files)
    - /api/oem/ceo-briefing       (4+ refs)
    - /api/oem/preparation/tomorrow (3+ refs)
    - /api/oem/whisper            (1+ ref)
  The Council routes (/api/council/*) have 0 frontend refs. So the C3/C7
  guards protect a surface that no user will ever hit.

SOLUTION:
  Port the C3/C7 guards into the legacy paths. This module provides a shared
  helper that applies both guards to any response dict, regardless of whether
  it came from AskPipeline, CEO briefing, or PreparationEngine.

  This is approach (b) from the audit: "port the C3/C7 guards into the legacy
  AskPipeline and oem.py routes." It's the right call for pilot safety because
  it protects users WITHOUT requiring a risky surface migration to the Council
  routes (which still have known engine gaps: Test 1 = 73.5%, Test 2 = 70%).

GUARDS:
  C3 (ACL): if ANY source signal is restricted (metadata["source_acl"] !=
  "public") and the user doesn't have access, redact the response text fields.
  Reuses propagate_acl_restrictions + redact_restricted_content from
  acl_barrier.py — same logic, same redaction text, same audit trail.

  C7 (tombstone): filter out any falsified patterns from the response. The
  legacy ActiveCognitionResolver already skips FALSIFIED patterns, but this
  is belt-and-suspenders: if any pattern reference in the response has a
  falsified status, strip it.

Usage:
  from maestro_api.legacy_guards import apply_legacy_guards

  # At the end of any legacy /api/oem/* route handler:
  response_dict = apply_legacy_guards(
      response_dict,
      source_signals=oem_state.signals,
      user_email=user_email,
      candidate_store=candidate_pattern_store,
  )
  return response_dict
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def apply_legacy_guards(
    response: dict[str, Any],
    source_signals: list[Any] = None,
    user_email: str = "",
    candidate_store: Any = None,
) -> dict[str, Any]:
    """Apply C3 (ACL) + C7 (tombstone) guards to a legacy API response.

    This is the single entry point for legacy path protection. Call it at
    every /api/oem/* response boundary, right before `return`.

    Args:
        response: the response dict from AskPipeline / briefing / preparation
        source_signals: the OEM signals that backed the response (for ACL check)
        user_email: the requesting user's email (for ACL access check)
        candidate_store: the CandidatePatternStore (for tombstone check)

    Returns:
        The same dict with guards applied. If ACL-restricted, text fields
        are redacted. If falsified patterns are found, they're stripped.
    """
    if not isinstance(response, dict):
        return response

    source_signals = source_signals or []

    # ── C3: ACL on derived intelligence ────────────────────────────────
    response = _apply_c3_acl_guard(response, source_signals, user_email)

    # ── C7: Tombstone — filter falsified patterns ──────────────────────
    response = _apply_c7_tombstone_guard(response, candidate_store)

    return response


# ════════════════════════════════════════════════════════════════════════════
# C3: ACL on derived intelligence
# ════════════════════════════════════════════════════════════════════════════

def _apply_c3_acl_guard(
    response: dict[str, Any],
    source_signals: list[Any],
    user_email: str,
) -> dict[str, Any]:
    """Apply C3 ACL guard: propagate restrictions + redact if needed.

    Reuses the Council's acl_barrier module so the redaction logic is
    identical across Council and legacy paths — no divergence.
    """
    try:
        from maestro_cognitive_council.acl_barrier import (
            propagate_acl_restrictions,
            redact_restricted_content,
        )

        response = propagate_acl_restrictions(response, source_signals, user_email)
        if response.get("acl_restricted", False):
            response = redact_restricted_content(response)
            logger.info(
                "C3 LEGACY GUARD: response redacted for user %s — %d restricted source(s)",
                user_email or "anonymous",
                len(response.get("acl_restricted_sources", [])),
            )
    except ImportError:
        logger.debug("C3 legacy guard: acl_barrier module unavailable, skipping")
    except Exception as e:
        logger.debug("C3 legacy guard failed (non-fatal): %s", e)

    return response


# ════════════════════════════════════════════════════════════════════════════
# C7: Falsified pattern tombstone
# ════════════════════════════════════════════════════════════════════════════

def _apply_c7_tombstone_guard(
    response: dict[str, Any],
    candidate_store: Any,
) -> dict[str, Any]:
    """Apply C7 tombstone guard: strip any falsified pattern references.

    The legacy ActiveCognitionResolver already skips FALSIFIED patterns
    when surfacing learned insights. This is belt-and-suspenders: if any
    pattern reference somehow made it into the response with a falsified
    status, strip it.

    Checks:
      1. The "evidence" list — if any evidence item references a falsified
         pattern, remove it
      2. The "answer" text — if it contains hypothesis text from a falsified
         pattern, append a tombstone notice
      3. The "active_insights" / "learned_insights" field — filter out any
         falsified patterns
    """
    if candidate_store is None:
        return response

    try:
        falsified_hypotheses = _get_falsified_hypotheses(candidate_store)
        if not falsified_hypotheses:
            return response

        # 1. Filter evidence list
        if "evidence" in response and isinstance(response["evidence"], list):
            response["evidence"] = [
                e for e in response["evidence"]
                if not _evidence_references_falsified(e, falsified_hypotheses)
            ]

        # 2. Filter active_insights / learned_insights
        for field in ("active_insights", "learned_insights", "insights"):
            if field in response and isinstance(response[field], list):
                response[field] = [
                    i for i in response[field]
                    if not _insight_is_falsified(i, falsified_hypotheses)
                ]

        # 3. Check answer text for falsified hypothesis text
        answer = response.get("answer", "")
        if isinstance(answer, str) and answer:
            for hyp in falsified_hypotheses:
                if hyp.lower() in answer.lower():
                    # Append tombstone notice (don't delete — the user should
                    # know a previously-learned pattern was falsified)
                    if "[FALSIFIED]" not in answer:
                        response["answer"] = (
                            answer + "\n\n[TOMBSTONE] A previously learned "
                            "pattern referenced in this answer has been "
                            "falsified and should not be relied upon."
                        )
                        logger.info(
                            "C7 LEGACY GUARD: tombstone notice appended — "
                            "falsified pattern '%.60s' found in answer",
                            hyp,
                        )
                    break

    except Exception as e:
        logger.debug("C7 legacy guard failed (non-fatal): %s", e)

    return response


def _get_falsified_hypotheses(candidate_store: Any) -> list[str]:
    """Get the hypothesis text of all falsified patterns in the store."""
    hypotheses = []
    try:
        for candidate in candidate_store.get_all():
            status = getattr(candidate, "status", None)
            status_val = getattr(status, "value", str(status)) if status else ""
            if status_val == "FALSIFIED":
                hyp = getattr(candidate, "hypothesis", "")
                if hyp:
                    hypotheses.append(hyp)
    except Exception:
        pass
    return hypotheses


def _evidence_references_falsified(evidence: Any, falsified_hypotheses: list[str]) -> bool:
    """Check if an evidence item references a falsified pattern."""
    if not isinstance(evidence, dict):
        return False
    text = (evidence.get("text", "") or evidence.get("source", "") or "").lower()
    return any(hyp.lower() in text for hyp in falsified_hypotheses)


def _insight_is_falsified(insight: Any, falsified_hypotheses: list[str]) -> bool:
    """Check if an insight item is a falsified pattern."""
    if isinstance(insight, dict):
        hyp = insight.get("hypothesis", "")
        if hyp and hyp in falsified_hypotheses:
            return True
    elif isinstance(insight, str):
        if insight in falsified_hypotheses:
            return True
    return False
