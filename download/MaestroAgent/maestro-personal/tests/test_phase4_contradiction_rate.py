"""Phase 4 contradiction-rate test — runs the harness and enforces <=2%."""

import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "evaluation"))

from cross_surface_contradiction_harness import _run_contradiction_harness


class TestPhase4ContradictionRate:
    """The roadmap requires <=2% cross-surface contradiction rate."""

    def test_contradiction_rate_meets_target(self):
        report = _run_contradiction_harness()
        assert report["met_target"], (
            f"Cross-surface contradiction rate {report['contradiction_rate']:.1%} "
            f"exceeds target {report['target']:.1%} "
            f"({report['contradictions']}/{report['total_checks']} contradictions). "
            f"Details: {report['details'][:5]}"
        )

    def test_harness_runs_all_stories_and_cutoffs(self):
        """The harness must cover 10 stories x 7 cutoffs = 70 snapshots
        x 2 surfaces = 140 checks."""
        report = _run_contradiction_harness()
        assert report["stories"] == 10
        assert report["cutoffs_per_story"] == 7
        assert report["total_checks"] == 140

    def test_harness_reports_details_on_failure(self):
        """When contradictions exist, the harness must report details."""
        report = _run_contradiction_harness()
        if report["contradictions"] > 0:
            assert len(report["details"]) > 0, \
                "Contradictions found but no details reported"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
