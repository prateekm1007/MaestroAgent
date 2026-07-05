"""Multi-tenant isolation tests for prediction lifecycle.

Principle 7: any fix that changes shared/global state into scoped state must
ship with a test that creates two instances of the scope (two orgs) and proves
they cannot see each other's data.

The predictions table has an `organization` column, but the query methods
(get_pending_predictions, get_prediction, list_predictions) historically did
NOT filter by it — creating the illusion of isolation without the reality.
These tests prove the isolation is real by creating predictions for two orgs
and verifying org A can never see org B's predictions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from maestro_oem.prediction_lifecycle import PredictionRecorder


@pytest.fixture
def two_org_recorders(tmp_path: Path) -> tuple[PredictionRecorder, PredictionRecorder]:
    """Two PredictionRecorder instances scoped to different orgs, same DB.

    This simulates two tenants sharing infrastructure. If isolation is broken,
    org A's predictions leak into org B's queries.
    """
    db_path = str(tmp_path / "predictions.db")
    org_a = PredictionRecorder(db_path=db_path, org_id="org_a")
    org_b = PredictionRecorder(db_path=db_path, org_id="org_b")
    return org_a, org_b


def test_prediction_org_a_does_not_leak_into_org_b(
    two_org_recorders: tuple[PredictionRecorder, PredictionRecorder],
) -> None:
    """A prediction created by org A must NOT appear in org B's queries.

    Proof by negation: if the queries don't filter by org_id, org B's
    get_pending_predictions() will return org A's prediction — a cross-tenant
    data leak. This test FAILS on the pre-fix code (no org_id filtering) and
    PASSES after the fix.
    """
    org_a, org_b = two_org_recorders

    # Org A creates a prediction.
    pred_id = org_a.create_prediction(
        prediction_type="recommendation",
        entity_id="hire_count",
        recommendation="Increase team size by 2",
        expected_outcome="faster delivery",
        confidence=0.8,
        organization="org_a",
    )

    # Org B must NOT see org A's prediction in any query.
    b_pending = org_b.get_pending_predictions()
    assert all(p["organization"] != "org_a" for p in b_pending), (
        f"Cross-tenant leak: org B sees org A's prediction. "
        f"Found {[p['prediction_id'] for p in b_pending if p.get('organization') == 'org_a']}"
    )

    # Org B must NOT be able to fetch org A's prediction by ID.
    b_direct = org_b.get_prediction(pred_id)
    assert b_direct is None, (
        f"Cross-tenant leak: org B fetched org A's prediction by ID. "
        f"Got prediction for org {b_direct.get('organization')}"
    )


def test_prediction_org_b_does_not_leak_into_org_a(
    two_org_recorders: tuple[PredictionRecorder, PredictionRecorder],
) -> None:
    """Symmetric check: org B's predictions must not leak into org A."""
    org_a, org_b = two_org_recorders

    org_b.create_prediction(
        prediction_type="risk",
        entity_id="burnout",
        recommendation="Reduce meeting load",
        expected_outcome="lower attrition",
        confidence=0.7,
        organization="org_b",
    )

    a_pending = org_a.get_pending_predictions()
    assert all(p["organization"] != "org_b" for p in a_pending), (
        "Cross-tenant leak: org A sees org B's prediction"
    )


def test_prediction_list_predictions_filters_by_org(
    two_org_recorders: tuple[PredictionRecorder, PredictionRecorder],
) -> None:
    """list_predictions() must only return predictions for the scoped org."""
    org_a, org_b = two_org_recorders

    # Create 3 predictions for A, 2 for B.
    for i in range(3):
        org_a.create_prediction(
            prediction_type="recommendation", entity_id=f"a_{i}",
            recommendation=f"rec_{i}", expected_outcome="ok", confidence=0.5,
            organization="org_a",
        )
    for i in range(2):
        org_b.create_prediction(
            prediction_type="risk", entity_id=f"b_{i}",
            recommendation=f"rec_{i}", expected_outcome="ok", confidence=0.5,
            organization="org_b",
        )

    a_all = org_a.list_predictions(limit=100)
    b_all = org_b.list_predictions(limit=100)

    assert all(p["organization"] == "org_a" for p in a_all), (
        f"org A list_predictions returned non-org-A predictions: "
        f"{[p['organization'] for p in a_all]}"
    )
    assert all(p["organization"] == "org_b" for p in b_all), (
        f"org B list_predictions returned non-org-B predictions: "
        f"{[p['organization'] for p in b_all]}"
    )
    assert len(a_all) == 3
    assert len(b_all) == 2


def test_prediction_default_org_still_works(tmp_path: Path) -> None:
    """Without an explicit org_id, the default org must still function.

    This guards the backward-compatibility path — existing single-tenant
    deployments must not break."""
    lc = PredictionRecorder(db_path=str(tmp_path / "default.db"), org_id="default")
    pred_id = lc.create_prediction(
        prediction_type="recommendation", entity_id="x",
        recommendation="y", expected_outcome="z", confidence=0.5,
    )
    assert lc.get_prediction(pred_id) is not None
    assert len(lc.get_pending_predictions()) >= 1
