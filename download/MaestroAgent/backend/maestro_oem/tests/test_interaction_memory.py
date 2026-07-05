"""Priority 3: Interaction Memory — the full lifecycle of how an exec
engages with a Whisper.

CEO directive (2026-07-04):
> Remember shown/opened/dismissed/deferred/acted/delegated/contradicted/
> resolved — not just whisper content.

The current WhisperHistoryStore tracks a SINGLE `action_taken` field that
gets overwritten. There's no event log — no way to know the sequence:
"shown → opened → deferred → shown again → acted". The CEO wants 8
distinct event types tracked as an append-only log.

The 8 event types:
  1. SHOWN       — Whisper was surfaced to the exec
  2. OPENED      — exec expanded/opened the Whisper (engagement signal)
  3. DISMISSED   — exec explicitly dismissed it (different from "never opened")
  4. DEFERRED    — exec snoozed/deferred it (intent to revisit)
  5. ACTED       — exec took action based on the Whisper
  6. DELEGATED   — exec delegated the action to someone else
  7. CONTRADICTED — exec disagreed with the Whisper (negative feedback)
  8. RESOLVED    — the situation resolved (commitment kept, objection withdrawn, etc.)

This enriches the AttributionAnalyzer (Priority 1) because:
  - "shown but never opened" ≠ "opened but dismissed" ≠ "opened, deferred, then acted"
  - The current exec_action="ignored" is too coarse — it conflates 3 different
    engagement patterns that have different attribution implications
  - The governed adaptation loop can form better hypotheses when it knows
    the full interaction history

Adversarial tests (write first, watch fail, then build):

  1. test_interaction_memory_exists
     InteractionMemory must exist and be importable.

  2. test_interaction_event_types
     All 8 event types must be defined: SHOWN, OPENED, DISMISSED, DEFERRED,
     ACTED, DELEGATED, CONTRADICTED, RESOLVED.

  3. test_interaction_memory_persists
     Events must survive restart (SQLite-backed).

  4. test_interaction_memory_append_only
     Recording a new event does NOT overwrite previous events. The full
     sequence is preserved.

  5. test_interaction_memory_full_lifecycle
     A full lifecycle (shown → opened → deferred → shown → acted → resolved)
     is recorded as 6 separate events with timestamps.

  6. test_interaction_memory_distinguishes_dismissed_from_never_opened
     "shown but never opened" must be distinguishable from "shown, opened,
     dismissed." The get_interaction_summary() method must report these
     differently.

  7. test_attribution_analyzer_uses_interaction_history
     The AttributionAnalyzer must accept an interaction_history parameter
     and use it to form richer hypotheses. "shown, opened, deferred, then
     broken" should produce a different hypothesis than "shown, never
     opened, broken."

  8. test_wiring_p11_interaction_in_whisper_py
     P11: whisper.py must reference InteractionMemory (to record SHOWN events).

  9. test_wiring_p11_interaction_in_governed_adaptation
     P11: governed_adaptation.py must reference InteractionMemory or
     interaction_history (AttributionAnalyzer uses it).

  10. test_interaction_memory_backward_compat
      Existing WhisperHistoryStore.record_shown() and record_outcome()
      must still work. InteractionMemory is ADDITIVE — it doesn't replace
      the existing store, it enriches it.

  11. test_interaction_summary_for_attribution
      get_interaction_summary() must return a structured summary that
      the AttributionAnalyzer can consume: final_state, opened_count,
      deferred_count, acted, delegated, contradicted, resolved.

P2: Untested code is unverified code.
P11: Wiring proved by grep + execution.
P13: Interaction events are DERIVED from real user actions, not caller-supplied.
"""
from __future__ import annotations

import sys
import inspect
import pytest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ═══ Priority 3: Interaction Memory ═════════════════════════════════════════

# ─── 1. InteractionMemory exists ───────────────────────────────────────────

def test_interaction_memory_exists():
    """InteractionMemory must exist and be importable."""
    from maestro_oem.interaction_memory import InteractionMemory
    assert InteractionMemory is not None


# ─── 2. All 8 event types defined ──────────────────────────────────────────

def test_interaction_event_types():
    """All 8 event types must be defined: SHOWN, OPENED, DISMISSED, DEFERRED,
    ACTED, DELEGATED, CONTRADICTED, RESOLVED."""
    from maestro_oem.interaction_memory import InteractionEventType

    expected = {"SHOWN", "OPENED", "DISMISSED", "DEFERRED",
                "ACTED", "DELEGATED", "CONTRADICTED", "RESOLVED"}
    actual = {e.name for e in InteractionEventType}
    assert expected.issubset(actual), (
        f"Must define all 8 event types. Missing: {expected - actual}. Got: {actual}"
    )


# ─── 3. Persistence (SQLite) ───────────────────────────────────────────────

def test_interaction_memory_persists(tmp_path):
    """Events must survive restart (SQLite-backed)."""
    from maestro_oem.interaction_memory import InteractionMemory, InteractionEventType

    db_path = str(tmp_path / "interactions.db")
    mem1 = InteractionMemory(db_path)
    mem1.record("wspr-1", InteractionEventType.SHOWN, org_id="default")
    mem1.record("wspr-1", InteractionEventType.OPENED, org_id="default")
    mem1.close()

    mem2 = InteractionMemory(db_path)
    history = mem2.get_history("wspr-1", org_id="default")
    assert len(history) == 2, (
        f"Must recover 2 events after restart. Got: {len(history)}"
    )
    assert history[0]["event_type"] == InteractionEventType.SHOWN.value
    assert history[1]["event_type"] == InteractionEventType.OPENED.value
    mem2.close()


# ─── 4. Append-only (never overwrite) ──────────────────────────────────────

def test_interaction_memory_append_only(tmp_path):
    """Recording a new event does NOT overwrite previous events. The full
    sequence is preserved."""
    from maestro_oem.interaction_memory import InteractionMemory, InteractionEventType

    mem = InteractionMemory(str(tmp_path / "interactions.db"))
    mem.record("wspr-1", InteractionEventType.SHOWN, org_id="default")
    mem.record("wspr-1", InteractionEventType.OPENED, org_id="default")
    mem.record("wspr-1", InteractionEventType.DISMISSED, org_id="default")
    mem.record("wspr-1", InteractionEventType.SHOWN, org_id="default")  # shown again

    history = mem.get_history("wspr-1", org_id="default")
    assert len(history) == 4, (
        f"Must have 4 events (append-only, no overwrite). Got: {len(history)}"
    )
    # Sequence must be preserved
    events = [h["event_type"] for h in history]
    expected = [
        InteractionEventType.SHOWN.value,
        InteractionEventType.OPENED.value,
        InteractionEventType.DISMISSED.value,
        InteractionEventType.SHOWN.value,
    ]
    assert events == expected, (
        f"Event sequence must be preserved. Got: {events}"
    )


# ─── 5. Full lifecycle ─────────────────────────────────────────────────────

def test_interaction_memory_full_lifecycle(tmp_path):
    """A full lifecycle (shown → opened → deferred → shown → acted → resolved)
    is recorded as 6 separate events with timestamps."""
    from maestro_oem.interaction_memory import InteractionMemory, InteractionEventType

    mem = InteractionMemory(str(tmp_path / "interactions.db"))
    lifecycle = [
        InteractionEventType.SHOWN,
        InteractionEventType.OPENED,
        InteractionEventType.DEFERRED,
        InteractionEventType.SHOWN,
        InteractionEventType.ACTED,
        InteractionEventType.RESOLVED,
    ]
    for event in lifecycle:
        mem.record("wspr-lifecycle", event, org_id="default")

    history = mem.get_history("wspr-lifecycle", org_id="default")
    assert len(history) == 6, f"Must record 6 events. Got: {len(history)}"

    # Each event must have a timestamp
    for h in history:
        assert h.get("timestamp"), f"Event must have timestamp. Got: {h}"


# ─── 6. Distinguishes dismissed from never opened ─────────────────────────

def test_interaction_memory_distinguishes_dismissed_from_never_opened(tmp_path):
    """'shown but never opened" must be distinguishable from "shown, opened,
    dismissed." The get_interaction_summary() method must report these
    differently."""
    from maestro_oem.interaction_memory import InteractionMemory, InteractionEventType

    mem = InteractionMemory(str(tmp_path / "interactions.db"))

    # Whisper A: shown but never opened
    mem.record("wspr-A", InteractionEventType.SHOWN, org_id="default")

    # Whisper B: shown, opened, dismissed
    mem.record("wspr-B", InteractionEventType.SHOWN, org_id="default")
    mem.record("wspr-B", InteractionEventType.OPENED, org_id="default")
    mem.record("wspr-B", InteractionEventType.DISMISSED, org_id="default")

    summary_A = mem.get_interaction_summary("wspr-A", org_id="default")
    summary_B = mem.get_interaction_summary("wspr-B", org_id="default")

    assert summary_A["opened_count"] == 0, "Whisper A was never opened"
    assert summary_B["opened_count"] == 1, "Whisper B was opened once"
    assert summary_A["final_state"] != summary_B["final_state"], (
        f"Final states must differ. A: {summary_A['final_state']}, B: {summary_B['final_state']}"
    )


# ─── 7. AttributionAnalyzer uses interaction history ──────────────────────

def test_attribution_analyzer_uses_interaction_history():
    """The AttributionAnalyzer must accept an interaction_history parameter
    and use it to form richer hypotheses. 'shown, opened, deferred, then
    broken' should produce a different hypothesis than 'shown, never
    opened, broken.'"""
    from maestro_oem.governed_adaptation import AttributionAnalyzer

    analyzer = AttributionAnalyzer()

    # Case 1: shown, never opened, broken
    outcome_1 = {
        "whisper_shown": True,
        "exec_action": "ignored",
        "outcome": "commitment_broken",
        "entity": "TestCorp",
        "context_signals": [],
        "interaction_history": [
            {"event_type": "SHOWN", "timestamp": "2026-07-01T10:00:00Z"},
        ],
    }
    analysis_1 = analyzer.analyze(outcome_1)

    # Case 2: shown, opened, deferred, broken
    outcome_2 = {
        "whisper_shown": True,
        "exec_action": "ignored",
        "outcome": "commitment_broken",
        "entity": "TestCorp",
        "context_signals": [],
        "interaction_history": [
            {"event_type": "SHOWN", "timestamp": "2026-07-01T10:00:00Z"},
            {"event_type": "OPENED", "timestamp": "2026-07-01T10:05:00Z"},
            {"event_type": "DEFERRED", "timestamp": "2026-07-01T10:10:00Z"},
        ],
    }
    analysis_2 = analyzer.analyze(outcome_2)

    # The hypotheses should differ — "never opened" vs "opened but deferred"
    # have different attribution implications
    assert analysis_1["hypothesis"] != analysis_2["hypothesis"], (
        f"Hypotheses must differ for 'never opened' vs 'opened, deferred'. "
        f"Got identical: {analysis_1['hypothesis']!r}"
    )


# ─── 8. P11: whisper.py references InteractionMemory ───────────────────────

def test_wiring_p11_interaction_in_whisper_py():
    """P11: whisper.py must reference InteractionMemory (to record SHOWN events)."""
    from maestro_oem import whisper
    source = inspect.getsource(whisper)
    assert "InteractionMemory" in source or "interaction_memory" in source, (
        "whisper.py must reference InteractionMemory (P11 — wired to record SHOWN events)"
    )


# ─── 9. P11: governed_adaptation.py uses interaction history ───────────────

def test_wiring_p11_interaction_in_governed_adaptation():
    """P11: governed_adaptation.py must reference InteractionMemory or
    interaction_history (AttributionAnalyzer uses it)."""
    from maestro_oem import governed_adaptation
    source = inspect.getsource(governed_adaptation)
    assert "interaction_history" in source or "InteractionMemory" in source, (
        "governed_adaptation.py must reference interaction_history (P11 — AttributionAnalyzer uses it)"
    )


# ─── 10. Backward compat ───────────────────────────────────────────────────

def test_interaction_memory_backward_compat():
    """Existing WhisperHistoryStore.record_shown() and record_outcome()
    must still work. InteractionMemory is ADDITIVE — it doesn't replace
    the existing store, it enriches it."""
    from maestro_oem.whisper_history_store import WhisperHistoryStore

    store = WhisperHistoryStore(":memory:")
    # These must still work without any InteractionMemory
    store.record_shown("wspr-1", insight="test insight", org_id="default")
    store.record_outcome("wspr-1", action="acted", org_id="default")
    history = store.get_all_history(org_id="default")
    assert "wspr-1" in history, "WhisperHistoryStore must still work (backward compat)"


# ─── 11. get_interaction_summary for attribution ──────────────────────────

def test_interaction_summary_for_attribution(tmp_path):
    """get_interaction_summary() must return a structured summary that
    the AttributionAnalyzer can consume: final_state, opened_count,
    deferred_count, acted, delegated, contradicted, resolved."""
    from maestro_oem.interaction_memory import InteractionMemory, InteractionEventType

    mem = InteractionMemory(str(tmp_path / "interactions.db"))
    # Record a rich lifecycle
    for event in [InteractionEventType.SHOWN, InteractionEventType.OPENED,
                  InteractionEventType.DEFERRED, InteractionEventType.SHOWN,
                  InteractionEventType.ACTED, InteractionEventType.RESOLVED]:
        mem.record("wspr-rich", event, org_id="default")

    summary = mem.get_interaction_summary("wspr-rich", org_id="default")

    required_fields = {"final_state", "opened_count", "deferred_count",
                       "acted", "delegated", "contradicted", "resolved", "shown_count"}
    actual_fields = set(summary.keys())
    assert required_fields.issubset(actual_fields), (
        f"Summary must include all required fields. Missing: {required_fields - actual_fields}. "
        f"Got: {actual_fields}"
    )
    assert summary["shown_count"] == 2, f"Shown twice. Got: {summary['shown_count']}"
    assert summary["opened_count"] == 1, f"Opened once. Got: {summary['opened_count']}"
    assert summary["deferred_count"] == 1, f"Deferred once. Got: {summary['deferred_count']}"
    assert summary["acted"] is True, "Acted must be True"
    assert summary["resolved"] is True, "Resolved must be True"
    assert summary["final_state"] == "RESOLVED", (
        f"Final state must be RESOLVED. Got: {summary['final_state']}"
    )
