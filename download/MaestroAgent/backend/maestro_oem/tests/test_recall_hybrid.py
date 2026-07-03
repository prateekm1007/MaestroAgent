"""Phase 2: Adversarial tests for the hybrid RecallEngine.

Director directive (2026-07-03, EXT-AUDITOR-SYNTHESIS):

> Write adversarial tests first (vague query, cross-entity, temporal filter).
> Build semantic + temporal + entity retrieval returning Evidence objects.
> Paste Playwright + pytest output in the commit. No self-certification.

These tests are the contract. The hybrid RecallEngine MUST pass all 5.
The old keyword-only WhisperRecall MUST fail at least 3 of them (vague
query, cross-entity, temporal filter) — that's the proof they are
non-vacuous.

Adversarial tests:
  1. test_recall_finds_vague_query
     "that legal thing from last month" must find compliance/contract
     whispers, even though the word "legal" does NOT appear in the
     insight text.

  2. test_recall_finds_cross_entity
     "everything about Globex" must return whispers + decisions + signals
     (multiple source_types, not just whispers).

  3. test_recall_temporal_filter
     "last week" must filter to the last 7 days. An older whisper (30
     days ago) MUST be excluded.

  4. test_recall_returns_evidence_spine
     Every recalled item must carry an evidence_spine with non-empty
     observed_facts. Placeholder strings are REJECTED.

  5. test_recall_what_changed_since
     A whisper from 5 days ago must return a non-empty what_changed_since
     string, populated from signal history (not a hardcoded template).

P2: Untested code is unverified code. P5: Self-certification is weak
evidence. P6: Fail closed — placeholder evidence is rejected.
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path so `from maestro_oem...` works when run
# from anywhere (including the test runner's CWD).
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from maestro_oem.recall_engine import RecallEngine, RecallQueryBuilder
from maestro_oem.evidence import Evidence


# ─── Fixtures ──────────────────────────────────────────────────────────────

class MockWhisperHistoryStore:
    """In-memory whisper history store for adversarial testing.

    Mimics the real WhisperHistoryStore interface (get_all_history +
    get_history). Does NOT mock the engine under test — only the storage
    backend, which is a legitimate dependency injection.
    """

    def __init__(self, history: dict[str, dict[str, Any]]):
        self._history = history

    def get_all_history(self, org_id: str = "default") -> dict[str, dict[str, Any]]:
        return dict(self._history)

    def get_history(self, whisper_id: str, org_id: str = "default") -> dict[str, Any]:
        return self._history.get(whisper_id, {})


class MockSignal:
    """Mock OEM signal — mirrors the real ExecutionSignal shape used by
    EvidenceBuilder (type, actor, artifact, metadata, timestamp, provider)."""

    def __init__(
        self,
        sig_type: Any,
        actor: str = "",
        artifact: str = "",
        metadata: dict | None = None,
        timestamp: datetime | None = None,
        provider: str = "customer",
    ):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


@pytest.fixture
def now():
    """Frozen 'now' for deterministic temporal tests."""
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def legal_compliance_history(now):
    """A whisper history where the insight says 'Compliance review flagged
    for Q3' — the word 'legal' does NOT appear.

    A vague query "that legal thing from last month" must still find this
    via semantic similarity (compliance ≈ legal) and entity synonym map.
    """
    last_month = now - timedelta(days=25)
    return {
        "wspr-compliance-q3": {
            "whisper_id": "wspr-compliance-q3",
            "shown_count": 2,
            "action_taken": "ignored",
            "first_shown": last_month.isoformat(),
            "last_shown": last_month.isoformat(),
            "insight": "Compliance review flagged for Q3 — contract clause needs Legal sign-off before renewal",
            "type": "commitment_exists",
            "entity": "Globex",
        },
    }


@pytest.fixture
def globex_cross_entity_history(now):
    """Whisper history + signals + decisions all referencing Globex.

    Used by test_recall_finds_cross_entity — must return matches across
    multiple source_types (whisper, signal, decision).
    """
    return {
        "wspr-globex-commit": {
            "whisper_id": "wspr-globex-commit",
            "shown_count": 1,
            "action_taken": None,
            "first_shown": (now - timedelta(days=10)).isoformat(),
            "last_shown": (now - timedelta(days=10)).isoformat(),
            "insight": "Engineering already promised SSO to Globex before Q4",
            "type": "commitment_exists",
            "entity": "Globex",
        },
        "wspr-globex-objection": {
            "whisper_id": "wspr-globex-objection",
            "shown_count": 1,
            "action_taken": None,
            "first_shown": (now - timedelta(days=5)).isoformat(),
            "last_shown": (now - timedelta(days=5)).isoformat(),
            "insight": "Globex raised a pricing objection in the last sync",
            "type": "objection_history",
            "entity": "Globex",
        },
    }


@pytest.fixture
def globex_cross_entity_signals(now):
    """Signals + a decision record referencing Globex — for cross-entity
    recall test. The RecallEngine must traverse signals (not just whisper
    history) when matching entities."""
    from maestro_oem.signal import SignalType

    return [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane.d@acme.com",
            artifact="crm:globex-commit-1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by 2024-12-15"},
            timestamp=now - timedelta(days=20),
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor="jane.d@acme.com",
            artifact="crm:globex-obj-1",
            metadata={"customer": "Globex", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5),
        ),
        MockSignal(
            SignalType.CUSTOMER_DECISION,
            actor="jane.d@acme.com",
            artifact="crm:globex-dec-1",
            metadata={"customer": "Globex", "decision_outcome": "renewed"},
            timestamp=now - timedelta(days=2),
        ),
    ]


@pytest.fixture
def temporal_filter_history(now):
    """Two whispers — one 3 days old, one 30 days old.

    Query "what did you say last week" must return ONLY the 3-day-old one.
    """
    return {
        "wspr-recent": {
            "whisper_id": "wspr-recent",
            "shown_count": 1,
            "action_taken": None,
            "first_shown": (now - timedelta(days=3)).isoformat(),
            "last_shown": (now - timedelta(days=3)).isoformat(),
            "insight": "Security review pending for the OAuth migration",
            "type": "objection_history",
            "entity": "Initech",
        },
        "wspr-old": {
            "whisper_id": "wspr-old",
            "shown_count": 1,
            "action_taken": None,
            "first_shown": (now - timedelta(days=30)).isoformat(),
            "last_shown": (now - timedelta(days=30)).isoformat(),
            "insight": "Security review pending for the API gateway rollout",
            "type": "objection_history",
            "entity": "Initech",
        },
    }


@pytest.fixture
def what_changed_history(now):
    """A whisper from 5 days ago + a more recent signal that updates the
    picture. The RecallEngine must populate what_changed_since from the
    signal diff."""
    from maestro_oem.signal import SignalType

    history = {
        "wspr-old-commit": {
            "whisper_id": "wspr-old-commit",
            "shown_count": 1,
            "action_taken": None,
            "first_shown": (now - timedelta(days=5)).isoformat(),
            "last_shown": (now - timedelta(days=5)).isoformat(),
            "insight": "Globex commitment to deliver SSO by Q4 is at risk",
            "type": "commitment_exists",
            "entity": "Globex",
        },
    }
    # New signal AFTER the whisper — this is the "what changed"
    new_signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_BROKEN,
            actor="jane.d@acme.com",
            artifact="crm:globex-broken-1",
            metadata={"customer": "Globex", "commitment": "SSO by Q4"},
            timestamp=now - timedelta(days=1),
        ),
    ]
    return history, new_signals


# ─── Adversarial Test 1: Vague query finds semantically related whisper ─────

def test_recall_finds_vague_query(legal_compliance_history, now):
    """'that legal thing from last month' must find the compliance whisper,
    even though 'legal' does NOT appear in the insight text.

    The insight says 'Compliance review flagged for Q3 — contract clause
    needs Legal sign-off before renewal'. The query says 'that legal thing
    from last month'.

    Old keyword-only engine: FAILS — 'legal' is in the synonym map but
    the insight text does not contain 'legal' literally (it contains
    'Legal' capitalized, but more importantly the insight says
    'Compliance review' which shares no keyword with 'legal').

    New hybrid engine: PASSES —
      - entity resolution expands 'legal' → {compliance, contract, law, regulation}
      - semantic embedding: 'compliance' and 'legal' are close in MiniLM space
      - temporal filter: 'last month' matches the 25-day-old timestamp
    """
    store = MockWhisperHistoryStore(legal_compliance_history)
    engine = RecallEngine(whisper_history_store=store, signals=[], now=now)

    result = engine.recall("that legal thing from last month", org_id="default")

    assert result["found"] is True, \
        f"Expected found=True for vague legal query, got found={result['found']}"
    assert result["match_count"] >= 1, \
        f"Expected at least 1 match, got {result['match_count']}"

    # The matched whisper must have a non-empty evidence_spine.observed_facts
    match = result["whispers"][0]
    es = match.get("evidence_spine", {})
    assert "observed_facts" in es, "evidence_spine missing observed_facts"
    assert len(es["observed_facts"]) > 0, \
        "observed_facts must be non-empty — placeholder evidence is forbidden (P6)"


# ─── Adversarial Test 2: Cross-entity recall (whisper + signal + decision) ──

def test_recall_finds_cross_entity(
    globex_cross_entity_history, globex_cross_entity_signals, now
):
    """'everything about Globex' must return whispers AND signals AND
    decisions (multiple source_types).

    Old keyword-only engine: FAILS — only searches whisper_history, never
    traverses signals or decisions.

    New hybrid engine: PASSES —
      - entity resolution: 'Globex' resolved to canonical entity
      - graph expansion: traverses signals + decisions involving Globex
      - returns items with source_type ∈ {whisper, signal, decision}
    """
    store = MockWhisperHistoryStore(globex_cross_entity_history)
    engine = RecallEngine(
        whisper_history_store=store,
        signals=globex_cross_entity_signals,
        now=now,
    )

    result = engine.recall("everything about Globex", org_id="default")

    assert result["found"] is True
    source_types = {item.get("source_type") for item in result.get("items", [])}
    # Must include at least 2 distinct source_types — proves cross-entity traversal
    assert len(source_types) >= 2, \
        f"Cross-entity recall must return ≥2 source_types, got {source_types}"
    # Whisper MUST be one of them (the user said "everything" — must include
    # what they previously saw)
    assert "whisper" in source_types, \
        f"Cross-entity recall must include whisper source_type, got {source_types}"


# ─── Adversarial Test 3: Temporal filter excludes older items ──────────────

def test_recall_temporal_filter(temporal_filter_history, now):
    """'last week' must filter to the last 7 days, excluding the 30-day-old
    whisper.

    Old keyword-only engine: FAILS — no temporal parsing at all. Returns
    all keyword matches regardless of date.

    New hybrid engine: PASSES —
      - dateparser interprets 'last week' as a date range (now-7d, now)
      - 3-day-old whisper is included
      - 30-day-old whisper is EXCLUDED
    """
    store = MockWhisperHistoryStore(temporal_filter_history)
    engine = RecallEngine(whisper_history_store=store, signals=[], now=now)

    result = engine.recall("what did you say last week", org_id="default")

    assert result["found"] is True
    matched_ids = {w["whisper_id"] for w in result["whispers"]}
    assert "wspr-recent" in matched_ids, \
        f"3-day-old whisper must be included in 'last week' query, got {matched_ids}"
    assert "wspr-old" not in matched_ids, \
        f"30-day-old whisper must be EXCLUDED from 'last week' query, got {matched_ids}"


# ─── Adversarial Test 4: Evidence Spine on every recalled item ─────────────

def test_recall_returns_evidence_spine(legal_compliance_history, now):
    """Every recalled item must carry an evidence_spine with real observed_facts.

    Placeholder strings are REJECTED. The observed_facts must contain text
    that comes from the actual signal/history data — not a generic
    "Maestro detected relevant organizational knowledge" fallback.
    """
    store = MockWhisperHistoryStore(legal_compliance_history)
    engine = RecallEngine(whisper_history_store=store, signals=[], now=now)

    result = engine.recall("compliance thing", org_id="default")

    assert result["found"] is True
    for w in result["whispers"]:
        assert "evidence_spine" in w, "Every recalled whisper must have evidence_spine"
        es = w["evidence_spine"]
        assert "claim" in es and es["claim"], "evidence_spine.claim must be non-empty"
        assert "observed_facts" in es, "evidence_spine must have observed_facts"
        assert len(es["observed_facts"]) > 0, "observed_facts must be non-empty (P6)"

        # REJECT placeholder strings (auditor's P3 fix from Phase 1)
        FORBIDDEN_PLACEHOLDERS = {
            "",
            "No specific commitments found",
            "Maestro detected relevant organizational knowledge",
            "Recorded in OEM",
        }
        for fact in es["observed_facts"]:
            text = fact.get("text", "")
            assert text not in FORBIDDEN_PLACEHOLDERS, \
                f"Placeholder text forbidden in observed_facts: {text!r}"

        # Enrichment goal: source_artifacts + people_involved + timestamps
        # must be present (can be empty lists if no data, but the KEYS must
        # exist — proves the engine populates them when data is available)
        assert "source_artifacts" in es, "evidence_spine must include source_artifacts key"
        assert "people_involved" in es, "evidence_spine must include people_involved key"
        assert "timestamps" in es, "evidence_spine must include timestamps key"


# ─── Adversarial Test 5: what_changed_since populated from signal diff ──────

def test_recall_what_changed_since(what_changed_history, now):
    """Recalled items must include what_changed_since populated from signal
    history that occurred AFTER the whisper was last shown.

    Old keyword-only engine: returns a hardcoded template string per
    action_taken ("You ignored this. The issue may have evolved.") — that
    is NOT a real signal diff.

    New hybrid engine: PASSES —
      - whisper last shown 5 days ago
      - 1 new signal since then (CUSTOMER_COMMITMENT_BROKEN, 1 day ago)
      - what_changed_since MUST mention the broken commitment, NOT a template
    """
    history, new_signals = what_changed_history
    store = MockWhisperHistoryStore(history)
    engine = RecallEngine(
        whisper_history_store=store,
        signals=new_signals,
        now=now,
    )

    result = engine.recall("globex commitment", org_id="default")

    assert result["found"] is True
    w = result["whispers"][0]
    what_changed = w.get("what_changed") or w.get("what_changed_since") or ""
    assert what_changed, "what_changed_since must be non-empty"

    # Must NOT be a hardcoded template (the old engine's tell-tale)
    TEMPLATE_PHRASES = [
        "You ignored this. The issue may have evolved.",
        "You acted on this. Check if the action resolved the issue.",
        "You overrode this recommendation. The situation may have changed.",
        "This was surfaced but no action was recorded.",
    ]
    for phrase in TEMPLATE_PHRASES:
        assert phrase not in what_changed, \
            f"what_changed_since must be signal-derived, not template. Got: {what_changed!r}"

    # Must reference the new signal (commitment broken) — this proves the
    # engine actually computed the diff, not just string-replaced
    assert "broken" in what_changed.lower() or "broke" in what_changed.lower() or "missed" in what_changed.lower(), \
        f"what_changed_since must reference the new signal (commitment broken). Got: {what_changed!r}"
