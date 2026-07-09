"""
P7 isolation test for PersonalPredictionMarket.

Verifies that the per-user scoping fix actually prevents cross-user data
leakage. This is the test the prior implementation lacked — the shared
mutable class variable ``_predictions: dict = {}`` would have leaked
predictions across users in a multi-tenant deployment.

Per P22: this test executes the production path (create_prediction,
resolve_prediction, get_predictions, get_calibration) with TWO users
and proves they cannot see each other's data.
"""

import pytest


class TestPredictionMarketIsolation:
    """P7: two users must not see each other's predictions."""

    def setup_method(self) -> None:
        """Clear all predictions before each test (test isolation)."""
        from maestro_personal.prediction_market import PersonalPredictionMarket
        PersonalPredictionMarket.clear(None)  # clear ALL users

    def teardown_method(self) -> None:
        """Clear all predictions after each test (don't leak to other tests)."""
        from maestro_personal.prediction_market import PersonalPredictionMarket
        PersonalPredictionMarket.clear(None)

    def test_two_users_isolated_create(self) -> None:
        """User A's predictions must not appear in User B's list."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        # User A creates a prediction
        pred_a = PersonalPredictionMarket.create_prediction(
            "Will I finish the book?", 0.7, user_id="user_a"
        )

        # User B creates a prediction
        pred_b = PersonalPredictionMarket.create_prediction(
            "Will I run a marathon?", 0.3, user_id="user_b"
        )

        # User A sees only their own
        preds_a = PersonalPredictionMarket.get_predictions(user_id="user_a")
        assert len(preds_a) == 1
        assert preds_a[0].prediction_id == pred_a.prediction_id
        assert preds_a[0].question == "Will I finish the book?"

        # User B sees only their own
        preds_b = PersonalPredictionMarket.get_predictions(user_id="user_b")
        assert len(preds_b) == 1
        assert preds_b[0].prediction_id == pred_b.prediction_id
        assert preds_b[0].question == "Will I run a marathon?"

    def test_two_users_isolated_resolve(self) -> None:
        """User B must not be able to resolve User A's prediction."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        # User A creates a prediction
        pred_a = PersonalPredictionMarket.create_prediction(
            "Will I finish the book?", 0.7, user_id="user_a"
        )

        # User B tries to resolve User A's prediction — must fail (return None)
        resolved = PersonalPredictionMarket.resolve_prediction(
            pred_a.prediction_id, "yes", user_id="user_b"
        )
        assert resolved is None

        # User A resolves their own — must succeed
        resolved_a = PersonalPredictionMarket.resolve_prediction(
            pred_a.prediction_id, "yes", user_id="user_a"
        )
        assert resolved_a is not None
        assert resolved_a.outcome == "yes"

    def test_two_users_isolated_calibration(self) -> None:
        """User A's calibration must not include User B's predictions."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        # User A creates and resolves 2 predictions
        p1 = PersonalPredictionMarket.create_prediction("A1", 0.9, user_id="user_a")
        PersonalPredictionMarket.resolve_prediction(p1.prediction_id, "yes", user_id="user_a")
        p2 = PersonalPredictionMarket.create_prediction("A2", 0.3, user_id="user_a")
        PersonalPredictionMarket.resolve_prediction(p2.prediction_id, "no", user_id="user_a")

        # User B creates and resolves 5 predictions
        for i in range(5):
            pb = PersonalPredictionMarket.create_prediction(
                f"B{i}", 0.5, user_id="user_b"
            )
            PersonalPredictionMarket.resolve_prediction(pb.prediction_id, "yes", user_id="user_b")

        # User A's calibration shows 2 resolved, not 7
        cal_a = PersonalPredictionMarket.get_calibration(user_id="user_a")
        assert cal_a["total"] == 2

        # User B's calibration shows 5 resolved, not 7
        cal_b = PersonalPredictionMarket.get_calibration(user_id="user_b")
        assert cal_b["total"] == 5

    def test_clear_one_user_does_not_clear_others(self) -> None:
        """Clearing User A must not affect User B's predictions."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        PersonalPredictionMarket.create_prediction("A1", 0.7, user_id="user_a")
        PersonalPredictionMarket.create_prediction("B1", 0.8, user_id="user_b")

        # Clear only User A
        PersonalPredictionMarket.clear(user_id="user_a")

        # User A has 0
        assert len(PersonalPredictionMarket.get_predictions(user_id="user_a")) == 0
        # User B still has 1
        assert len(PersonalPredictionMarket.get_predictions(user_id="user_b")) == 1

    def test_clear_all_users(self) -> None:
        """Clear(None) wipes all users — test teardown helper."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        PersonalPredictionMarket.create_prediction("A1", 0.7, user_id="user_a")
        PersonalPredictionMarket.create_prediction("B1", 0.8, user_id="user_b")

        PersonalPredictionMarket.clear(None)

        assert len(PersonalPredictionMarket.get_predictions(user_id="user_a")) == 0
        assert len(PersonalPredictionMarket.get_predictions(user_id="user_b")) == 0

    def test_default_user_id_backward_compat(self) -> None:
        """Existing tests that don't pass user_id still work via '__default__' slot."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        # No user_id passed — routes to __default__
        pred = PersonalPredictionMarket.create_prediction("Default user", 0.6)
        assert pred.user_probability == 0.6

        # get_predictions without user_id also routes to __default__
        preds = PersonalPredictionMarket.get_predictions()
        assert len(preds) == 1
        assert preds[0].prediction_id == pred.prediction_id

    def test_p25_insufficient_calibration_history_message(self) -> None:
        """P25: with <10 resolved predictions, message says 'insufficient calibration history'."""
        from maestro_personal.prediction_market import PersonalPredictionMarket

        # Only 2 resolved predictions — below the 10-prediction threshold
        p1 = PersonalPredictionMarket.create_prediction("Q1", 0.9, user_id="user_a")
        PersonalPredictionMarket.resolve_prediction(p1.prediction_id, "yes", user_id="user_a")
        p2 = PersonalPredictionMarket.create_prediction("Q2", 0.3, user_id="user_a")
        PersonalPredictionMarket.resolve_prediction(p2.prediction_id, "no", user_id="user_a")

        cal = PersonalPredictionMarket.get_calibration(user_id="user_a")
        assert cal["total"] == 2
        assert "Insufficient calibration history" in cal["message"]
        assert "10" in cal["message"]
        # average_brier is still computed (for internal use) but the message is honest
        assert cal["average_brier"] is not None
