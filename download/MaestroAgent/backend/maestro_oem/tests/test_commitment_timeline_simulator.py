"""Phase 2.2 — Commitment Timeline Simulator.

Adversarial tests written FIRST (P2). Watch them fail, then build.

External auditor's standard (from Loop 1.5 + the 6-Parameter Roadmap):
> "Track the commitment lifecycle Day-1 → Day-60. Don't just record what
> happened — project what will happen if the current pattern continues."

The CommitmentMutationTracker (Phase 1.5) records past mutations. The
CommitmentTimelineSimulator (Phase 2.2) DERIVES a forward projection
from that history. Critical design rule (P13): the simulator must NOT
accept the rate, pattern, risk, or recommendation as caller-supplied
inputs. Those are the conclusions. The valuable work is deriving them
from the actual mutation history. If the caller supplies the rate,
we've built a calculator pretending to be a capability.

Tests are adversarial: each assertion is non-vacuous (would fail on
the not-yet-built codebase). Write first, watch fail, then build.
"""
from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path
_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from maestro_oem.signal import SignalType


# ─── Mocks (legitimate DI — mirrors real ExecutionSignal shape) ────────────

class MockSignal:
    """Mirror of real ExecutionSignal shape (same as test_loop1_5.py)."""
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


def _commitment_signal(entity, text, days_ago, actor="jane.d@acme.com", artifact=None):
    return MockSignal(
        SignalType.CUSTOMER_COMMITMENT_MADE,
        actor=actor,
        artifact=artifact or f"crm:{entity}-{days_ago}",
        metadata={"customer": entity, "commitment": text},
        timestamp=datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc) - timedelta(days=days_ago),
    )


# ─── 1. Existence + interface ──────────────────────────────────────────────

def test_simulator_class_exists_and_importable():
    """The CommitmentTimelineSimulator must exist and be importable.

    Adversarial: would raise ImportError on the not-yet-built codebase.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    sim = CommitmentTimelineSimulator()
    assert sim is not None, "Simulator must instantiate"


def test_simulator_returns_timeline_projection_object(now):
    """simulate() returns an object with the required projection fields.

    Required fields per the design:
      - entity, pattern_type, mutation_rate_per_30d,
        projected_mutations_by_day_60, risk_level, baseline_trajectory,
        recommendation, evidence_summary
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    # Record at least one commitment so the simulator has something to project
    tracker.record_commitment(_commitment_signal("Globex", "Deliver SSO by 2024-12-15", days_ago=30))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Globex", horizon_days=60, now=now)

    for field in ("entity", "pattern_type", "mutation_rate_per_30d",
                  "projected_mutations_by_day_60", "risk_level",
                  "baseline_trajectory", "recommendation", "evidence_summary"):
        assert hasattr(projection, field), \
            f"TimelineProjection must have field '{field}'. Got: {dir(projection)}"


# ─── 2. P13 — Inputs are DERIVED, not caller-supplied ──────────────────────

def test_simulator_signature_does_not_accept_rate_or_pattern_as_input(now):
    """CRITICAL P13 test: simulate() must NOT accept rate, pattern, risk,
    or recommendation as input parameters.

    These are the CONCLUSIONS. If the caller can supply them, we've built
    a calculator pretending to be a capability (P13 violation). The
    simulator must derive them from the mutation history itself.
    """
    import inspect
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator

    sig = inspect.signature(CommitmentTimelineSimulator.simulate)
    forbidden_params = {"rate", "mutation_rate", "pattern", "pattern_type",
                        "risk", "risk_level", "recommendation"}
    actual_params = set(sig.parameters.keys())
    overlap = forbidden_params & actual_params
    assert not overlap, \
        f"simulate() must NOT accept conclusion-parameters as inputs (P13). " \
        f"Forbidden params found: {overlap}. Allowed: {actual_params}"


def test_simulator_derives_pattern_from_history_deadline_slippage(now):
    """When mutations show deadline moving later, pattern = deadline_slippage.

    The simulator must DERIVE this from comparing old_text vs new_text,
    not take it as a parameter. Old: "Deliver SSO by 2024-12-15".
    New:  "Deliver SSO by 2025-01-31". Date moved later → slippage.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    tracker.record_commitment(_commitment_signal("Globex", "Deliver SSO by 2024-12-15", days_ago=30))
    tracker.record_commitment(_commitment_signal("Globex", "Deliver SSO by 2025-01-31", days_ago=5))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Globex", now=now)

    assert projection.pattern_type == "deadline_slippage", \
        f"Deadline moving later must be classified as 'deadline_slippage'. " \
        f"Got: {projection.pattern_type}"


def test_simulator_derives_pattern_scope_expansion(now):
    """When mutations add new clauses/scope, pattern = scope_expansion.

    Old: "Deliver SSO by 2024-12-15"
    New:  "Deliver SSO + MFA by 2024-12-15"  (scope added, deadline unchanged)
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    tracker.record_commitment(_commitment_signal("Initech", "Deliver SSO by 2024-12-15", days_ago=30))
    tracker.record_commitment(_commitment_signal("Initech", "Deliver SSO + MFA by 2024-12-15", days_ago=5))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Initech", now=now)

    assert projection.pattern_type == "scope_expansion", \
        f"Adding scope (+ MFA) must be classified as 'scope_expansion'. " \
        f"Got: {projection.pattern_type}"


def test_simulator_classifies_volatile_when_3_plus_mutations_in_30_days(now):
    """When ≥3 mutations occur in 30 days, pattern = volatile.

    A stable relationship has ≤1 mutation. A volatile relationship has
    the customer moving the goalposts repeatedly. This is the strongest
    risk signal — Maestro must surface it.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    # 3 mutations in 30 days — volatile
    tracker.record_commitment(_commitment_signal("Hooli", "Deliver SSO by 2024-12-15", days_ago=30))
    tracker.record_commitment(_commitment_signal("Hooli", "Deliver SSO by 2025-01-15", days_ago=20))
    tracker.record_commitment(_commitment_signal("Hooli", "Deliver SSO by 2025-02-15", days_ago=10))
    tracker.record_commitment(_commitment_signal("Hooli", "Deliver SSO by 2025-03-15", days_ago=1))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Hooli", now=now)

    assert projection.pattern_type == "volatile", \
        f"3+ mutations in 30 days must be 'volatile'. Got: {projection.pattern_type}"
    assert projection.risk_level == "high", \
        f"Volatile pattern must produce 'high' risk. Got: {projection.risk_level}"


def test_simulator_returns_stable_when_no_mutations(now):
    """When only one commitment exists (no mutations), pattern = stable.

    Non-vacuous counter-test: don't cry wolf. A single commitment
    without changes is the LOWEST risk state.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    tracker.record_commitment(_commitment_signal("Umbrella", "Deliver SSO by 2024-12-15", days_ago=10))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Umbrella", now=now)

    assert projection.pattern_type == "stable", \
        f"No mutations → 'stable'. Got: {projection.pattern_type}"
    assert projection.risk_level == "low", \
        f"Stable pattern → 'low' risk. Got: {projection.risk_level}"
    assert projection.mutation_rate_per_30d == 0.0, \
        f"Zero mutations → rate 0.0. Got: {projection.mutation_rate_per_30d}"


# ─── 3. Projection math + recommendation ──────────────────────────────────

def test_simulator_projects_mutations_by_day_60(now):
    """projected_mutations_by_day_60 is derived from rate × time.

    Scenario: 2 mutations in 30 days → rate = 2.0/30d →
    projected over 60 days = ~4 mutations.

    The simulator must DERIVE this; the caller cannot supply it (P13).
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    tracker.record_commitment(_commitment_signal("Pied", "Deliver SSO by 2024-12-15", days_ago=30))
    tracker.record_commitment(_commitment_signal("Pied", "Deliver SSO by 2025-01-15", days_ago=20))
    tracker.record_commitment(_commitment_signal("Pied", "Deliver SSO by 2025-02-15", days_ago=10))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Pied", horizon_days=60, now=now)

    # 2 mutations in 30 days = 0.0667/day → over 60 days = ~4
    # Don't require exact match — require it's > 0 and derived from history
    assert projection.projected_mutations_by_day_60 > 0, \
        f"With 2 mutations in 30 days, projected mutations must be > 0. " \
        f"Got: {projection.projected_mutations_by_day_60}"
    assert projection.mutation_rate_per_30d > 0, \
        f"With 2 mutations in 30 days, rate must be > 0. Got: {projection.mutation_rate_per_30d}"


def test_simulator_recommendation_uses_pattern_not_caller_input(now):
    """The recommendation is DERIVED from pattern + risk, not caller-supplied.

    A 'volatile' pattern must produce a different recommendation than a
    'stable' pattern. The caller never specifies the recommendation.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    # Stable pattern
    stable_tracker = CommitmentMutationTracker()
    stable_tracker.record_commitment(_commitment_signal("Acme", "Deliver SSO by 2024-12-15", days_ago=10))
    stable_proj = CommitmentTimelineSimulator(tracker=stable_tracker).simulate("Acme", now=now)

    # Volatile pattern
    volatile_tracker = CommitmentMutationTracker()
    for i, text in enumerate([
        "Deliver SSO by 2024-12-15",
        "Deliver SSO by 2025-01-15",
        "Deliver SSO by 2025-02-15",
        "Deliver SSO by 2025-03-15",
    ]):
        volatile_tracker.record_commitment(_commitment_signal("Acme", text, days_ago=30 - i * 10))
    volatile_proj = CommitmentTimelineSimulator(tracker=volatile_tracker).simulate("Acme", now=now)

    assert stable_proj.recommendation != volatile_proj.recommendation, \
        f"Stable and volatile patterns must produce DIFFERENT recommendations " \
        f"(otherwise the recommendation isn't derived from the pattern). " \
        f"Stable: {stable_proj.recommendation!r}, Volatile: {volatile_proj.recommendation!r}"
    assert "volatile" in stable_proj.recommendation.lower() or \
           "volatile" in volatile_proj.recommendation.lower() or \
           "renegotiat" in volatile_proj.recommendation.lower() or \
           "lock" in volatile_proj.recommendation.lower() or \
           "stable" in stable_proj.recommendation.lower() or \
           "monitor" in stable_proj.recommendation.lower(), \
        f"Recommendations must reference the pattern (volatile→renegotiate/lock, stable→monitor). " \
        f"Stable: {stable_proj.recommendation!r}, Volatile: {volatile_proj.recommendation!r}"


def test_simulator_baseline_trajectory_has_day_checkpoints(now):
    """The baseline_trajectory must include Day 1, 7, 30, 60 checkpoints.

    Each checkpoint projects the commitment's state (on_track / at_risk /
    renegotiated / broken) at that point in time, derived from the
    pattern + rate.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    tracker.record_commitment(_commitment_signal("Globex", "Deliver SSO by 2024-12-15", days_ago=30))
    tracker.record_commitment(_commitment_signal("Globex", "Deliver SSO by 2025-01-31", days_ago=5))

    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("Globex", horizon_days=60, now=now)

    assert isinstance(projection.baseline_trajectory, list), \
        f"baseline_trajectory must be a list. Got: {type(projection.baseline_trajectory)}"
    assert len(projection.baseline_trajectory) >= 3, \
        f"baseline_trajectory must have ≥3 checkpoints (Day 1/7/30/60). " \
        f"Got: {len(projection.baseline_trajectory)}"

    # Each checkpoint must have at least day + projected_state
    for cp in projection.baseline_trajectory:
        assert "day" in cp, f"Each checkpoint must have 'day'. Got: {cp}"
        assert "projected_state" in cp, f"Each checkpoint must have 'projected_state'. Got: {cp}"
        assert cp["projected_state"] in ("on_track", "at_risk", "renegotiated", "broken", "unknown"), \
            f"projected_state must be a known enum value. Got: {cp['projected_state']}"


# ─── 4. Integration — wired into the production path (P11, P15) ───────────

def test_simulator_endpoint_reachable_via_oem_route(now):
    """P11/P15: the simulator must be wired into a real production endpoint.

    GET /loop1.5/timeline/{entity} must return the projection. If this
    endpoint doesn't exist, the module is a demonstration, not a
    capability (P11 violation).
    """
    from fastapi.testclient import TestClient
    from maestro_api.main import create_app

    # First record a commitment via the existing mutation record endpoint
    app = create_app(db_path=":memory:")
    client = TestClient(app)
    record_resp = client.post("/api/oem/loop1.5/mutation/record", json={
        "entity": "TestTimelineEntity",
        "commitment_text": "Deliver SSO by 2024-12-15",
        "actor": "test@acme.com",
        "artifact": "test:timeline-1",
    })
    assert record_resp.status_code == 200, \
        f"Setup: mutation record failed. Status: {record_resp.status_code}, Body: {record_resp.text}"

    # Now call the timeline endpoint
    resp = client.get("/api/oem/loop1.5/timeline/TestTimelineEntity")
    assert resp.status_code == 200, \
        f"GET /loop1.5/timeline/{{entity}} must return 200. " \
        f"Status: {resp.status_code}, Body: {resp.text[:500]}"

    data = resp.json()
    assert "entity" in data, f"Response must have 'entity'. Got: {data}"
    assert "pattern_type" in data, f"Response must have 'pattern_type'. Got: {data}"
    assert "risk_level" in data, f"Response must have 'risk_level'. Got: {data}"
    assert "recommendation" in data, f"Response must have 'recommendation'. Got: {data}"


def test_simulator_handles_entity_with_no_history_gracefully(now):
    """An entity with no commitment history must return a stable/low-risk
    projection, not raise an exception.

    This is the cold-start path — the simulator must fail closed and
    honest (P6), not silently swallow or 500.
    """
    from maestro_oem.commitment_timeline_simulator import CommitmentTimelineSimulator
    from maestro_oem.commitment_mutation_tracker import CommitmentMutationTracker

    tracker = CommitmentMutationTracker()
    sim = CommitmentTimelineSimulator(tracker=tracker)
    projection = sim.simulate("NonexistentEntity", now=now)

    assert projection.pattern_type == "stable", \
        f"No history → 'stable' (not raise). Got: {projection.pattern_type}"
    assert projection.risk_level == "low", \
        f"No history → 'low' risk. Got: {projection.risk_level}"
    assert projection.mutation_rate_per_30d == 0.0, \
        f"No history → rate 0.0. Got: {projection.mutation_rate_per_30d}"
