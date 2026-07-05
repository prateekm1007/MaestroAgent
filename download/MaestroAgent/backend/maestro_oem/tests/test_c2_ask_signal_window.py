"""C2 fix: Ask pipeline must search ALL signals, not just the first 30.

External auditor finding (Arena.ai audit at 8103ff6, verified at edc99c3):
> C2: Ask 30-signal window drops commitments at index 42.
> ask_pipeline.py:724 still has `for s in self._signals[:30]:`

The bug: when the user asks "What did we promise Globex?", the Ask
pipeline searches only the first 30 signals. If the Globex commitment
is at index ≥30 (which is common — Globex is the flagship customer and
has many signals), the pipeline returns "I don't know" while the data
exists in the system.

This is the highest-leverage one-line fix in the audit directive:
closing this single bug ALSO closes C3 (cross-surface coherence) for
the Ask surface, because the Ask surface will now see the same
commitments the Whisper and Today surfaces already see.

Test strategy: ingest 50+ signals where the Globex commitment is at
index 42 (matching the audit's exact scenario). Ask "What did we
promise Globex?". The pipeline MUST return the commitment. Before the
fix, it returns an empty "I don't know" answer.

Adversarial: written FIRST, watched fail, then fix applied (P2).
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class MockSignal:
    """Mirror of real ExecutionSignal shape (same as test_h3_ask_pipeline.py)."""
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()
        # C-003: default to public so the permission filter doesn't skip these
        self.source_acl = "public"


@pytest.fixture
def now():
    return datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _make_signals_with_globex_at_index_42(now):
    """Build a signal list where the Globex commitment is at index 42.

    This matches the audit's exact scenario: 50+ signals, Globex commitment
    at index 42, so the [:30] slice drops it.
    """
    from maestro_oem.signal import SignalType

    signals = []
    # Indices 0-41: 42 unrelated signals (objections, decisions, etc.)
    for i in range(42):
        signals.append(MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor=f"customer{i}@example.com",
            artifact=f"crm:noise-{i}",
            metadata={
                "customer": f"Customer{i}",
                "objection_type": "price",
                "text": f"Customer {i} objected to pricing",
            },
            timestamp=now - timedelta(days=40 - i),
        ))
    # Index 42: the Globex commitment (the one the user asks about)
    signals.append(MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-1",
        metadata={
            "customer": "Globex",
            "commitment": "Deliver SSO by 2024-12-15",
        },
        timestamp=now - timedelta(days=5),
    ))
    # Indices 43-49: 7 more noise signals
    for i in range(43, 50):
        signals.append(MockSignal(
            SignalType.DECISION_SIGNAL,
            actor=f"exec{i}@example.com",
            artifact=f"decision:noise-{i}",
            metadata={
                "customer": f"Customer{i}",
                "decision_outcome": "approved",
            },
            timestamp=now - timedelta(days=3),
        ))
    return signals


# ─── Tests ─────────────────────────────────────────────────────────────────

def test_ask_pipeline_finds_commitment_at_index_42(now):
    """C2 regression: when the Globex commitment is at index 42 (past the
    old [:30] window), the Ask pipeline must STILL find it.

    Before the fix: the pipeline iterated `self._signals[:30]` and missed
    the commitment at index 42 → returned "I don't know" → user lost
    trust in Maestro.

    After the fix: the pipeline iterates ALL signals and finds the
    commitment, returning it in the answer.
    """
    from maestro_oem.ask_pipeline import AskPipeline

    signals = _make_signals_with_globex_at_index_42(now)
    assert len(signals) == 50, f"Test setup: expected 50 signals, got {len(signals)}"
    # Verify the Globex commitment is at index 42 (the audit's exact scenario)
    globex_idx = None
    for i, s in enumerate(signals):
        if s.metadata.get("customer") == "Globex":
            globex_idx = i
            break
    assert globex_idx == 42, \
        f"Test setup: Globex commitment must be at index 42 (audit scenario). Got: {globex_idx}"

    pipeline = AskPipeline(signals=signals, whisper_store=None, oem_state=None)
    result = pipeline.execute("What did we promise Globex?")

    # The answer MUST mention the Globex commitment
    answer_text = (result.get("answer") or "").lower() if isinstance(result, dict) else str(result).lower()
    evidence = result.get("evidence", []) if isinstance(result, dict) else []

    # The commitment text MUST appear somewhere in the answer or evidence
    commitment_mentioned = "sso" in answer_text or "2024-12-15" in answer_text
    if not commitment_mentioned:
        # Check evidence too — the answer might reference it via citations
        for ev in evidence:
            ev_text = str(ev).lower()
            if "sso" in ev_text or "2024-12-15" in ev_text or "globex" in ev_text:
                commitment_mentioned = True
                break

    assert commitment_mentioned, \
        f"C2 REGRESSION: Ask pipeline must find the Globex commitment at index 42. " \
        f"Answer: {answer_text[:300]!r}. Evidence count: {len(evidence)}."


def test_ask_pipeline_no_artificial_signal_cap(now):
    """P14: confirm there is no artificial cap on signal iteration.

    This is the structural guard — if anyone re-introduces a `[:N]` slice,
    this test will catch it. We ingest 100 signals with the Globex
    commitment at index 99 (worst case) and verify it's still found.
    """
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.signal import SignalType

    signals = []
    for i in range(99):
        signals.append(MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor=f"customer{i}@example.com",
            artifact=f"crm:noise-{i}",
            metadata={"customer": f"Customer{i}", "objection_type": "price"},
            timestamp=now - timedelta(days=100 - i),
        ))
    signals.append(MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-commit-final",
        metadata={"customer": "Globex", "commitment": "Deliver SSO + MFA by 2025-03-31"},
        timestamp=now - timedelta(days=1),
    ))
    assert len(signals) == 100

    pipeline = AskPipeline(signals=signals, whisper_store=None, oem_state=None)
    result = pipeline.execute("What did we promise Globex?")
    answer_text = (result.get("answer") or "").lower() if isinstance(result, dict) else ""

    assert "mfa" in answer_text or "2025-03-31" in answer_text or "sso" in answer_text, \
        f"C2 REGRESSION at scale: Globex commitment at index 99 must be found. " \
        f"Answer: {answer_text[:300]!r}"


def test_ask_pipeline_performance_with_large_signal_set(now):
    """P14: confirm the fix doesn't introduce a performance regression.

    With 500 signals, the Ask pipeline must still return in <2 seconds
    (generous bound for test environments). Before the fix, the [:30]
    slice was a hidden performance "optimization" — removing it must not
    blow up latency.
    """
    import time
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.signal import SignalType

    signals = []
    for i in range(500):
        signals.append(MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor=f"customer{i}@example.com",
            artifact=f"crm:noise-{i}",
            metadata={"customer": f"Customer{i}", "objection_type": "price"},
            timestamp=now - timedelta(days=500 - i),
        ))
    # Globex commitment at the very end
    signals.append(MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor="jane.d@acme.com",
        artifact="crm:globex-final",
        metadata={"customer": "Globex", "commitment": "Deliver SSO by 2025-06-30"},
        timestamp=now,
    ))

    pipeline = AskPipeline(signals=signals, whisper_store=None, oem_state=None)
    t0 = time.time()
    result = pipeline.execute("What did we promise Globex?")
    elapsed = time.time() - t0

    assert elapsed < 2.0, \
        f"C2 fix performance regression: Ask pipeline took {elapsed:.3f}s with 500 signals " \
        f"(must be <2s). The fix must not introduce latency."
