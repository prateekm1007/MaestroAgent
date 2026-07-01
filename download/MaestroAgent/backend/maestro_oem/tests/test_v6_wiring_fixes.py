"""
Round-25 wiring-fix regression tests.

Two gaps the Round-24 audit flagged as PARTIAL are now closed:

1. BackgroundAdaptationLoop must run on every live_ingest(), not only when
   the GET /api/oem/background-loop endpoint is hit (V6 Law 2: "improves
   even when nobody opens Maestro").

2. wisdom.py must reference OrganizationalDNA — recommendations that don't
   match the org's DNA are flagged as "against your nature" (V6 Spec #5
   filter that was missing).

These tests prove both wires are live and stay live.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from maestro_oem import OEMEngine
from maestro_oem.signal import ExecutionSignal, SignalType
from maestro_oem.wisdom import WisdomEngine


# ============================================================
# Helpers
# ============================================================

def _make_signal(signal_type: SignalType, actor: str = "u@acme.com",
                 artifact: str = "X-1", domain: str = "engineering") -> ExecutionSignal:
    return ExecutionSignal(
        type=signal_type,
        timestamp=datetime.now(timezone.utc),
        actor=actor,
        artifact=artifact,
        metadata={"domain": domain},
    )


# ============================================================
# Fix #1 — BackgroundAdaptationLoop hooks into live_ingest()
# ============================================================

class TestBackgroundLoopWiredToLiveIngest:
    """V6 Law 2: the organization improves even when nobody opens Maestro.

    The BackgroundAdaptationLoop must run on every signal ingest, not only
    when GET /api/oem/background-loop is called. We verify this by calling
    live_ingest() and checking that the cached result is populated.
    """

    def test_live_ingest_triggers_background_loop(self) -> None:
        """live_ingest() must populate _last_background_loop_result."""
        # Use a fake OEMState-like object that has the live_ingest path
        # wired the same way the real one does. We import the real module
        # and inspect that the call chain exists.
        from maestro_api.oem_state import OEMState
        state = OEMState()
        state.initialize()

        sig = _make_signal(SignalType.PR_OPENED, artifact="PR-1")
        state.live_ingest([sig])

        # The cache must be populated by live_ingest, proving the loop ran.
        assert state._last_background_loop_result is not None, (
            "live_ingest() did not run the BackgroundAdaptationLoop — "
            "V6 Law 2 violated: the loop only runs when the API is called."
        )
        assert "notices" in state._last_background_loop_result
        assert "summary" in state._last_background_loop_result
        assert state._last_background_loop_at is not None

    def test_background_loop_runs_on_every_ingest(self) -> None:
        """Each live_ingest() call must refresh the background-loop cache."""
        from maestro_api.oem_state import OEMState
        state = OEMState()
        state.initialize()

        # First ingest
        state.live_ingest([_make_signal(SignalType.PR_OPENED, artifact="PR-A")])
        first_at = state._last_background_loop_at
        assert first_at is not None

        # Second ingest must refresh the timestamp
        import time
        time.sleep(0.05)  # ensure timestamp differs
        state.live_ingest([_make_signal(SignalType.PR_OPENED, artifact="PR-B")])
        second_at = state._last_background_loop_at
        assert second_at is not None
        assert second_at > first_at, (
            "Second live_ingest() did not refresh the background-loop cache — "
            "the loop only ran once."
        )

    def test_background_loop_failure_does_not_break_ingest(self) -> None:
        """A background-loop failure must never break signal ingest."""
        from maestro_api.oem_state import OEMState
        state = OEMState()
        state.initialize()

        # Monkey-patch _run_background_loop to raise — ingest must still succeed.
        def _boom() -> None:
            raise RuntimeError("simulated loop failure")

        state._run_background_loop = _boom  # type: ignore[assignment]

        sig = _make_signal(SignalType.PR_OPENED, artifact="PR-X")
        # Must NOT raise — the loop failure is swallowed.
        state.live_ingest([sig])

        # Signal was still ingested.
        assert len(state.signals) >= 1
        assert state._live_signals_ingested >= 1

    def test_live_ingest_source_file_references_background_loop(self) -> None:
        """Static check: oem_state.py source must reference the background loop.

        This catches regressions where someone removes the wire in a refactor.
        """
        import maestro_api.oem_state as mod
        source = open(mod.__file__).read()
        assert "BackgroundAdaptationLoop" in source, (
            "oem_state.py no longer references BackgroundAdaptationLoop — "
            "the wire from live_ingest() to the background loop has been cut."
        )
        assert "_run_background_loop" in source, (
            "oem_state.py no longer defines _run_background_loop() — "
            "the live_ingest() hook is gone."
        )


# ============================================================
# Fix #2 — wisdom.py references DNA alignment
# ============================================================

class TestWisdomDNAAlignment:
    """V6 Spec #5 wiring: wisdom.py references OrganizationalDNA.

    Recommendations that don't match the org's DNA are flagged as
    "against your nature."
    """

    def test_wisdom_returns_dna_alignment_field(self) -> None:
        """synthesize() must return a dna_alignment field."""
        engine = OEMEngine()
        model = engine.get_model()
        w = WisdomEngine(model, [])
        result = w.synthesize(context="launch")
        assert "dna_alignment" in result, (
            "wisdom.synthesize() does not return dna_alignment — "
            "DNA is not filtering recommendations (V6 Spec #5 wire missing)."
        )
        dna = result["dna_alignment"]
        assert "alignment_score" in dna
        assert "votes_cast" in dna
        assert "aligned_chromosomes" in dna
        assert "misaligned_chromosomes" in dna
        assert "per_chromosome" in dna

    def test_wisdom_returns_against_your_nature_flag(self) -> None:
        """synthesize() must return a against_your_nature boolean."""
        engine = OEMEngine()
        model = engine.get_model()
        w = WisdomEngine(model, [])
        result = w.synthesize(context="launch")
        assert "against_your_nature" in result
        assert isinstance(result["against_your_nature"], bool)

    def test_aggressive_org_flags_launch_wisdom_as_against_nature(self) -> None:
        """An aggressive org (8/10 PRs merged) should flag 'wait for compliance' as against its nature."""
        signals = []
        for i in range(8):
            signals.append(_make_signal(SignalType.PR_MERGED, artifact=f"PR-M-{i}"))
        for i in range(2):
            signals.append(_make_signal(SignalType.PR_OPENED, artifact=f"PR-O-{i}"))

        engine = OEMEngine()
        for s in signals:
            engine.ingest([s])
        model = engine.get_model()

        w = WisdomEngine(model, signals)
        result = w.synthesize(context="launch")

        # The launch wisdom says "accepted slightly lower velocity for compliance certainty"
        # → contains "wait" and "compliance" → misaligned with aggressive risk_appetite.
        dna = result["dna_alignment"]
        assert dna["votes_cast"] >= 1, "Expected at least one chromosome to vote."
        assert "risk_appetite" in dna["misaligned_chromosomes"], (
            f"Expected risk_appetite to vote misaligned for an aggressive org; "
            f"got misaligned={dna['misaligned_chromosomes']}"
        )
        assert result["against_your_nature"] is True, (
            "An aggressive org should flag 'wait for compliance' as against its nature."
        )
        assert "[AGAINST YOUR NATURE]" in result["recommendation"]

    def test_cautious_org_does_not_flag_launch_wisdom(self) -> None:
        """A cautious org (1/10 PRs merged) should NOT flag 'wait for compliance' as against its nature.

        Note: the launch wisdom text mentions BOTH 'wait' (align with cautious)
        and 'rushed' (misalign with cautious, because it appears in contrast:
        "launches that rushed Legal review failed"). So risk_appetite may vote
        neutral (mixed signal) — that's correct matrix behavior. The spec
        requirement is only that the cautious org is NOT flagged as
        against_your_nature, which means risk_appetite must NOT vote misaligned.
        """
        signals = []
        for i in range(9):
            signals.append(_make_signal(SignalType.PR_OPENED, artifact=f"PR-O-{i}"))
        for i in range(1):
            signals.append(_make_signal(SignalType.PR_MERGED, artifact=f"PR-M-{i}"))

        engine = OEMEngine()
        for s in signals:
            engine.ingest([s])
        model = engine.get_model()

        w = WisdomEngine(model, signals)
        result = w.synthesize(context="launch")

        dna = result["dna_alignment"]
        # risk_appetite must NOT vote misaligned for a cautious org reading
        # 'wait for compliance' wisdom. It may vote aligned or neutral.
        assert "risk_appetite" not in dna["misaligned_chromosomes"], (
            f"A cautious org should NOT have risk_appetite vote misaligned on "
            f"'wait for compliance' wisdom; per_chrom={dna['per_chromosome'].get('risk_appetite')}"
        )
        assert result["against_your_nature"] is False, (
            "A cautious org should NOT be flagged as against its nature for "
            "'wait for compliance' wisdom."
        )
        assert "[AGAINST YOUR NATURE]" not in result["recommendation"]

    def test_wisdom_source_file_references_dna(self) -> None:
        """Static check: wisdom.py source must reference OrganizationalDNA."""
        import maestro_oem.wisdom as mod
        source = open(mod.__file__).read()
        assert "OrganizationalDNA" in source, (
            "wisdom.py no longer references OrganizationalDNA — "
            "the wire from wisdom to DNA has been cut."
        )
        assert "organizational_dna" in source, (
            "wisdom.py no longer imports from organizational_dna — "
            "the DNA alignment filter has been removed."
        )
        assert "_compute_dna_alignment" in source, (
            "wisdom.py no longer defines _compute_dna_alignment() — "
            "the DNA alignment computation is gone."
        )

    def test_dna_alignment_matrix_covers_all_seven_chromosomes(self) -> None:
        """The alignment matrix must cover all 7 DNA chromosomes."""
        from maestro_oem.organizational_dna import OrganizationalDNA
        engine = OEMEngine()
        model = engine.get_model()
        dna = OrganizationalDNA(model, [])
        sequenced = dna.sequence()
        seven_chromosomes = set(sequenced["chromosomes"].keys())

        matrix_chromosomes = set(WisdomEngine._DNA_ALIGNMENT_MATRIX.keys())
        missing = seven_chromosomes - matrix_chromosomes
        assert not missing, (
            f"DNA alignment matrix is missing chromosomes: {missing}. "
            f"Every chromosome must have an alignment vote entry."
        )
