"""Phase 1.3 regression: graph must NOT count signal edges as active commitments.

The audit found 'Newsletter: 20 active commitments' because signal_observed
edges were counted as active commitments. Only edge_type='commitment' should
count. Also verifies the three completion-rate denominators.
"""
import os, sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

from maestro_personal_shell.personal_graph import PersonalGraph


def _fresh_graph():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="graph13_")
    tmp.close()
    return PersonalGraph(db_path=tmp.name, user_email="test@local")


def test_signal_edges_not_counted_as_commitments():
    """Phase 1.3: signal edges must NOT inflate active_commitments."""
    g = _fresh_graph()
    # Add 5 signal edges (should NOT count as commitments)
    for i in range(5):
        g.add_edge("Newsletter", "signal", topic=f"digest {i}", confidence=0.5)
    # Add 1 commitment edge (should count)
    g.add_edge("Newsletter", "commitment", topic="send proposal", confidence=0.8)

    summary = g.get_entity_summary("Newsletter")
    assert summary["active_commitments"] == 1, (
        f"Phase 1.3 FAIL: active_commitments={summary['active_commitments']} "
        f"(expected 1, not 6). Signal edges are being counted as commitments."
    )
    assert summary["total_interactions"] == 6, (
        f"total_interactions should be 6 (5 signal + 1 commitment)"
    )


def test_completion_rate_denominators():
    """Phase 1.3: three completion-rate denominators must be present."""
    g = _fresh_graph()
    # 3 commitments, 1 completed (hit), 1 broken (miss), 1 active
    g.add_edge("Acme", "commitment", topic="proposal")
    g.add_edge("Acme", "commitment", topic="contract")
    g.add_edge("Acme", "commitment", topic="review")
    g.update_outcome("Acme", "proposal", "hit")
    g.update_outcome("Acme", "contract", "miss")

    summary = g.get_entity_summary("Acme")
    # resolved = 2 (hit + miss), active = 1
    assert "resolved_completion_rate" in summary, "Missing resolved_completion_rate"
    assert "all_cohort_completion_rate" in summary, "Missing all_cohort_completion_rate"
    assert "overdue_active_rate" in summary, "Missing overdue_active_rate"

    # resolved_completion_rate = 1 hit / 2 resolved = 0.5
    assert summary["resolved_completion_rate"] == 0.5, (
        f"resolved_completion_rate={summary['resolved_completion_rate']} (expected 0.5)"
    )
    # all_cohort = 1 hit / 3 total commitments = 0.333
    assert abs(summary["all_cohort_completion_rate"] - 1/3) < 0.01, (
        f"all_cohort_completion_rate={summary['all_cohort_completion_rate']}"
    )
    # overdue_active = 1 active / 3 total = 0.333
    assert abs(summary["overdue_active_rate"] - 1/3) < 0.01, (
        f"overdue_active_rate={summary['overdue_active_rate']}"
    )


def test_newsletter_not_active_commitment():
    """Phase 1.3: the exact audit scenario — Newsletter must not show
    20 active commitments."""
    g = _fresh_graph()
    # Simulate 20 newsletter signals (what the audit found)
    for i in range(20):
        g.add_edge("TechNewsletter", "signal", topic=f"weekly digest {i}")
    summary = g.get_entity_summary("TechNewsletter")
    assert summary["active_commitments"] == 0, (
        f"Phase 1.3 FAIL: Newsletter shows {summary['active_commitments']} "
        f"active commitments (expected 0). This is the exact audit bug."
    )


if __name__ == "__main__":
    test_signal_edges_not_counted_as_commitments()
    print("Phase 1.3 test 1/3: signal edges not counted — PASS")
    test_completion_rate_denominators()
    print("Phase 1.3 test 2/3: completion-rate denominators — PASS")
    test_newsletter_not_active_commitment()
    print("Phase 1.3 test 3/3: Newsletter not active commitment — PASS")
    print("\nPhase 1.3 graph semantics tests PASSED")
