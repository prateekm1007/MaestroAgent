"""Phase 6 Trusted Silence tests — material transitions + ranking + dedupe."""

import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))

from maestro_personal_shell.material_transitions import (
    MATERIAL_TRANSITIONS,
    classify_transition,
    rank_deltas,
    dedupe_and_cooldown,
    clear_notification_history,
    COOLDOWN_HOURS,
)
from silence_benchmark_100 import get_silence_benchmark
from silence_eval import (
    evaluate_silence,
    evaluate_board_escalation_test,
    evaluate_resolved_stops_surfacing,
    evaluate_silence_when_nothing_useful,
)


class TestPhase6Benchmark:
    """The 100-opportunity Trusted Silence benchmark must exist."""

    def test_benchmark_has_100_opportunities(self):
        opps = get_silence_benchmark()
        assert len(opps) == 100

    def test_benchmark_has_4_labels(self):
        opps = get_silence_benchmark()
        labels = {o["label"] for o in opps}
        assert labels == {"interrupt_now", "next_summary", "on_demand_only", "say_nothing"}

    def test_benchmark_has_8_transition_types(self):
        """The roadmap defines 8 material transition types."""
        transitions = set(MATERIAL_TRANSITIONS.keys())
        assert "routine_activity" in transitions
        assert "new_high_consequence_commitment" in transitions
        assert "deadline_moved" in transitions
        assert "commitment_completed" in transitions
        assert "completion_disputed" in transitions
        assert "unresolved_dependency_appeared" in transitions
        assert "sentiment_worsened" in transitions
        assert "stale_but_important" in transitions
        assert "risk_resolved" in transitions


class TestPhase6TransitionClassifier:
    """The transition classifier must correctly identify transition types."""

    def test_newsletter_is_routine_activity(self):
        delta = {"text": "Weekly newsletter issue 5", "type": "newsletter"}
        assert classify_transition(delta) == "routine_activity"

    def test_board_escalation_is_high_consequence(self):
        delta = {"text": "Board escalation: investor wants emergency meeting",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "new_high_consequence_commitment"

    def test_completion_is_detected(self):
        delta = {"text": "The proposal has been sent successfully",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "commitment_completed"

    def test_dispute_is_detected(self):
        delta = {"text": "We got the proposal but it's missing the appendix",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "completion_disputed"

    def test_disputing_is_detected(self):
        delta = {"text": "Sam is disputing the timeline",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "completion_disputed"

    def test_deadline_moved_is_detected(self):
        delta = {"text": "The deadline moved from Friday to Monday",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "deadline_moved"

    def test_blocked_dependency_is_detected(self):
        delta = {"text": "We're blocked — legal hasn't signed off",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "unresolved_dependency_appeared"

    def test_sentiment_worsened_is_detected(self):
        delta = {"text": "The client is furious about the delay",
                 "type": "reported_statement"}
        assert classify_transition(delta) == "sentiment_worsened"


class TestPhase6Ranking:
    """The ranking system must rank by the 7 roadmap factors."""

    def test_board_escalation_outranks_newsletters(self):
        """100 newsletters + 1 board escalation → board escalation is #1."""
        clear_notification_history()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        deltas = [
            {"text": f"Weekly newsletter {i}", "entity": "NewsletterCorp",
             "type": "newsletter", "timestamp": now, "signal_id": f"n-{i}"}
            for i in range(100)
        ]
        deltas.append({
            "text": "Board escalation: investor emergency meeting",
            "entity": "Board", "type": "reported_statement",
            "timestamp": now, "signal_id": "board-001",
        })
        ranked = rank_deltas(deltas, user_email="test@x.com")
        assert ranked[0]["signal_id"] == "board-001"

    def test_routine_activity_never_surfaces(self):
        """Routine activity must NEVER be surfaced regardless of score."""
        clear_notification_history()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        deltas = [
            {"text": "Weekly newsletter", "entity": "News", "type": "newsletter",
             "timestamp": now, "signal_id": "n-1"},
        ]
        ranked = rank_deltas(deltas, user_email="test@x.com")
        surfaced = dedupe_and_cooldown(ranked, user_email="test@x.com")
        assert len(surfaced) == 0


class TestPhase6DedupeCooldown:
    """Dedupe + cooldown must prevent repeated notifications."""

    def test_dedupe_prevents_same_signal_twice(self):
        """The same signal_id must not be notified twice."""
        clear_notification_history()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        deltas = [{
            "text": "Board escalation: urgent", "entity": "Board",
            "type": "reported_statement", "timestamp": now, "signal_id": "sig-1",
        }]
        ranked = rank_deltas(deltas, user_email="test@x.com")
        # First pass: should surface
        first = dedupe_and_cooldown(ranked, user_email="test@x.com")
        assert len(first) == 1
        # Second pass: should NOT surface (dedupe)
        second = dedupe_and_cooldown(ranked, user_email="test@x.com")
        assert len(second) == 0

    def test_cooldown_prevents_same_entity_transition(self):
        """Same entity+transition within cooldown window is suppressed (across passes).

        Within a single pass, different signals for the same entity+transition
        are all surfaced (they're different events). But on the SECOND pass,
        the cooldown kicks in and nothing re-surfaces.
        """
        clear_notification_history()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        # Two different signals, same entity+transition
        deltas = [
            {"text": "Board escalation: urgent meeting", "entity": "Board",
             "type": "reported_statement", "timestamp": now, "signal_id": "sig-1"},
            {"text": "Board escalation: another urgent meeting", "entity": "Board",
             "type": "reported_statement", "timestamp": now, "signal_id": "sig-2"},
        ]
        ranked = rank_deltas(deltas, user_email="test@x.com")
        # First pass: both signals surface (different events, same pass)
        first = dedupe_and_cooldown(ranked, user_email="test@x.com")
        assert len(first) == 2
        # Second pass: nothing re-surfaces (cooldown + dedupe)
        second = dedupe_and_cooldown(ranked, user_email="test@x.com")
        assert len(second) == 0


class TestPhase6SilenceMetrics:
    """The 4 roadmap Trusted Silence metrics must meet targets."""

    def test_materiality_precision_meets_target(self):
        report = evaluate_silence()
        p = report["metrics"]["materiality_precision"]
        assert p["met"], \
            f"Materiality precision {p['value']} below target {p['target']} ({p['support']})"

    def test_critical_interruption_recall_meets_target(self):
        report = evaluate_silence()
        r = report["metrics"]["critical_interruption_recall"]
        assert r["met"], \
            f"Critical interruption recall {r['value']} below target {r['target']} ({r['support']})"

    def test_unnecessary_interruption_rate_meets_target(self):
        report = evaluate_silence()
        u = report["metrics"]["unnecessary_interruption_rate"]
        assert u["met"], \
            f"Unnecessary interruption rate {u['value']} exceeds target {u['target']} ({u['support']})"

    def test_repeated_notification_rate_meets_target(self):
        report = evaluate_silence()
        r = report["metrics"]["repeated_notification_rate"]
        assert r["met"], \
            f"Repeated notification rate {r['value']} exceeds target {r['target']} ({r['support']})"

    def test_say_nothing_items_never_surfaced(self):
        """Items labeled 'say_nothing' must NEVER be surfaced."""
        report = evaluate_silence()
        say_nothing = report["label_breakdown"]["say_nothing"]
        assert say_nothing["surfaced"] == 0, \
            f"{say_nothing['surfaced']} say_nothing items were surfaced (should be 0)"


class TestPhase6AcceptanceTests:
    """The 3 roadmap acceptance tests must pass."""

    def test_board_escalation_among_newsletters(self):
        """100 newsletters + 1 board escalation → board escalation surfaced,
        newsletters NOT surfaced."""
        result = evaluate_board_escalation_test()
        assert result["passed"], \
            f"Board escalation test failed: board_is_top={result['board_is_top_ranked']}, " \
            f"board_surfaced={result['board_surfaced']}, " \
            f"newsletters_surfaced={result['newsletters_surfaced']}"

    def test_resolved_stops_surfacing(self):
        """Resolved commitment stops surfacing (completion reported once)."""
        result = evaluate_resolved_stops_surfacing()
        assert result["passed"], \
            f"Resolved test failed: completion_surfaced={result['completion_surfaced']}"

    def test_silence_when_nothing_useful(self):
        """Silence is returned when nothing is useful (only noise)."""
        result = evaluate_silence_when_nothing_useful()
        assert result["passed"], \
            f"Silence test failed: surfaced_count={result['surfaced_count']} (should be 0)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
