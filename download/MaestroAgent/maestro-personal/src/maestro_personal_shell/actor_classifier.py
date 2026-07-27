"""Actor attribution classifier (P82 / FA33).

Root cause (P10): without this module, ingestion had no way to distinguish
"I will ..." (user commitment) from "Can you ...?" (request) from
"Nora: I will ..." (third-party commitment) — every sentence collapsed into
a user commitment. That was the audit's smoking gun.

P56: rules hold a veto over the LLM. This module is rules-only; no LLM call.
P85: classify_signal never raises.

Authored by: Kimi K3 (engineering lead) via CTO↔K3 loop (P46 verified)
CTO verification: P46 PASS — served_model=moonshotai/kimi-k3,
  generation_id=gen-1785178766-xPgmWBOBRrHXPLOOSBQR
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

VALID_ACTORS = ("user", "entity_name", "system")
VALID_EVENT_TYPES = (
    "commitment", "request", "question", "quotation",
    "cancellation", "completion", "tentative", "joke",
)

# --- rule patterns (evaluated in strict priority order; earlier rules veto later ones) ---

_JOKE_PATTERNS = [
    re.compile(r"\bjust kidding\b", re.I),
    re.compile(r"\bjk\b", re.I),
    re.compile(r"\bconquer mars\b", re.I),
    re.compile(r"\baliens?\b", re.I),
    re.compile(r"\blol\b|\bhaha\b", re.I),
]

_CANCELLATION_PATTERNS = [
    re.compile(r"\bwill not\b", re.I),
    re.compile(r"\bwon'?t\b", re.I),
    re.compile(r"\bcancell?ed\b", re.I),
    re.compile(r"\bcalled off\b", re.I),
    re.compile(r"\bno longer (going|able)\b", re.I),
    re.compile(r"\bscratch that\b", re.I),
]

_QUOTATION_PATTERNS = [
    re.compile(r"\bas\s+[A-Za-z]+\s+said\b", re.I),
    re.compile(r"\baccording to\b", re.I),
    re.compile(r"\b\w+\s+(said|wrote|stated|noted)\s*[:,]", re.I),
    re.compile(r"[\"'][^\"']+[\"']"),  # any quoted span
]

_REQUEST_PATTERNS = [
    re.compile(r"^(can|could|will|would|may|might)\s+you\b", re.I),
    re.compile(r"\bplease\s+(send|review|provide|share|give|forward)\b", re.I),
]

_HEDGE_PATTERNS = [
    re.compile(r"\bmaybe\b", re.I),
    re.compile(r"\bmight\b", re.I),
    re.compile(r"\bcould possibly\b", re.I),
    re.compile(r"\bsometime\b", re.I),
    re.compile(r"\bhopefully\b", re.I),
    re.compile(r"\btry to\b", re.I),
    re.compile(r"\bnot sure\b", re.I),
]

_COMPLETION_PATTERNS = [
    re.compile(r"\bi'?ve\s+(sent|finished|completed|delivered|shipped)\b", re.I),
    re.compile(r"\b(done|finished|completed|delivered|shipped)\b", re.I),
]

_COMMITMENT_PATTERNS = [
    re.compile(r"^i will\b", re.I),
    re.compile(r"\bi'?ll\b", re.I),
    re.compile(r"\bi\s+(shall|promise|commit to)\b", re.I),
]

_DEADLINE_PATTERN = re.compile(
    r"\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"tomorrow|eod|eow|end of (day|week)|\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{1,2})\b",
    re.I,
)

_SPEAKER_PREFIX = re.compile(r"^([A-Z][a-zA-Z]+)\s*:\s*(.+)$", re.S)
_COUNTERPARTY = re.compile(r"\bto\s+[A-Z][a-z]+\b")


def _result(actor, event_type, confidence, reasoning):
    return {
        "actor": actor,
        "event_type": event_type,
        "confidence": round(float(confidence), 3),
        "reasoning": reasoning,
    }


def _matches_any(patterns, text):
    return any(p.search(text) for p in patterns)


def _detect_actor(text, speaker_hint):
    """Return (actor, working_text, speaker_name). Only a 'Name:' prefix or an
    explicit hint flips attribution to entity_name; reported speech ('As Nora
    said, ...') keeps actor=user because the user is doing the reporting."""
    if speaker_hint:
        hint = str(speaker_hint).strip()
        if hint.lower() in ("user", "system"):
            return hint.lower(), text, None
        return "entity_name", text, hint
    m = _SPEAKER_PREFIX.match(text.strip())
    if m:
        return "entity_name", m.group(2).strip(), m.group(1)
    return "user", text, None


def classify_signal(text, speaker_hint=None, source_type="personal_email"):
    """Classify raw signal text -> {actor, event_type, confidence, reasoning}.

    P85: never raises; returns a zero-confidence system fallback on any error.
    """
    try:
        return _classify(text, speaker_hint, source_type)
    except Exception as exc:  # noqa: BLE001 — P85 mandates total containment
        logger.exception("classify_signal failed on text=%r", text)
        return _result("system", "commitment", 0.0, f"classification failed: {exc}")


def _classify(text, speaker_hint, source_type):
    if not text or not str(text).strip():
        return _result("system", "tentative", 0.0, "empty signal text")

    actor, body, speaker_name = _detect_actor(str(text).strip(), speaker_hint)

    # 1. Joke — vetoes commitment ("Just kidding, I will conquer Mars ...")
    if _matches_any(_JOKE_PATTERNS, body):
        return _result(actor, "joke", 0.6, "joke marker detected; not a real commitment")

    # 2. Cancellation — vetoes commitment ("I will not ...; cancelled")
    if _matches_any(_CANCELLATION_PATTERNS, body):
        explicit = bool(re.search(r"\bcancell?ed\b|\bcalled off\b", body, re.I))
        return _result(actor, "cancellation", 0.9 if explicit else 0.85,
                       "negation/cancellation keyword overrides commitment reading")

    # 3. Quotation / reported speech — vetoes commitment (FA33)
    if _matches_any(_QUOTATION_PATTERNS, body):
        return _result(actor, "quotation", 0.6, "quoted/reported speech, not a first-person promise")

    # 4. Request — ask directed at the reader
    if _matches_any(_REQUEST_PATTERNS, body):
        return _result(actor, "request", 0.65, "interrogative/imperative ask directed at reader")

    # 5. Question — interrogative without an action ask
    if body.rstrip().endswith("?"):
        return _result(actor, "question", 0.6, "question mark without an action request")

    # 6. Tentative — hedge language vetoes commitment
    if _matches_any(_HEDGE_PATTERNS, body):
        return _result(actor, "tentative", 0.6, "hedge language (maybe/might/sometime) weakens intent")

    # 7. Completion — past-tense delivery marker
    if _matches_any(_COMPLETION_PATTERNS, body):
        return _result(actor, "completion", 0.8, "past-tense completion/delivery marker")

    # 8. Commitment — explicit first-person promise
    if _matches_any(_COMMITMENT_PATTERNS, body):
        has_deadline = bool(_DEADLINE_PATTERN.search(body))
        has_counterparty = bool(_COUNTERPARTY.search(body)) or speaker_name is not None
        if has_deadline and has_counterparty:
            return _result(actor, "commitment", 0.9,
                           "explicit 'I will' + named counterparty + deadline")
        if has_deadline:
            return _result(actor, "commitment", 0.87, "explicit 'I will' + deadline")
        return _result(actor, "commitment", 0.75, "explicit 'I will' without a clear deadline")

    # Fallback — FA33: never default to commitment on ambiguity
    return _result(actor, "tentative", 0.3,
                   "no clear intent pattern matched; low-confidence non-commitment default")


def classify_and_append(text, user_email, entity, source_signal_id=None, db_path=None, source_type="personal_email", commitment_id=None):
    """Production ingestion path (P22: real append_event, no mocks).

    Classifies `text`, builds a CommitmentEvent, appends to the canonical
    ledger, and returns the event_id. This is what /api/signals calls.

    Args:
        text: the raw signal text to classify
        user_email: the user this signal belongs to
        entity: the entity the signal is about (e.g. "Nora")
        source_signal_id: FK to the signals table (provenance)
        db_path: optional DB path override
        source_type: 'personal_email' | 'newsletter' | 'notification' | 'self_generated' | ...
                    (used for P74 signal-to-noise filtering; stored in metadata)
        commitment_id: optional — group this event under an existing commitment
                       (e.g. a cancellation event for commitment c1 should pass
                       commitment_id='c1' so the reducer links them). If None,
                       a new UUID is generated (one event = one commitment).
                       The reconciliation layer (Phase 3+) will derive this
                       automatically by entity + text similarity matching.
    """
    from maestro_personal_shell.canonical_ledger import CommitmentEvent, append_event

    classification = classify_signal(text, source_type=source_type)
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Build metadata JSON safely (avoid quote-injection from reasoning text)
    import json
    metadata_obj = {
        "source_type": source_type or "personal_email",
        "reasoning": classification["reasoning"][:200],
    }
    metadata_str = json.dumps(metadata_obj, ensure_ascii=False)

    event = CommitmentEvent(
        event_id=event_id,
        commitment_id=commitment_id or event_id,  # group under existing commitment if provided
        actor=classification["actor"],
        event_type=classification["event_type"],
        entity=entity,
        text=text,
        source_signal_id=source_signal_id,
        confidence=classification["confidence"],
        state="active",
        user_email=user_email,
        timestamp=now,
        metadata=metadata_str,
    )

    try:
        return append_event(event, db_path=db_path)
    except Exception:
        logger.exception("append_event failed (signal=%s, classification=%s)",
                         source_signal_id, classification)
        raise
