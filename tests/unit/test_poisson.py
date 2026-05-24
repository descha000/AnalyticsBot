"""Unit tests for the Poisson goals model."""

import math

import pytest

from models.poisson import (
    GoalDistribution,
    _poisson_pmf,
    calculate_win_probabilities,
    expected_goals_distribution,
)


class TestPoissonPmf:
    def test_sums_to_one(self):
        pmf = _poisson_pmf(2.5, max_goals=20)
        assert abs(sum(pmf) - 1.0) < 1e-6

    def test_zero_lambda_all_probability_at_zero(self):
        pmf = _poisson_pmf(0.0, max_goals=5)
        assert pmf[0] == pytest.approx(1.0)
        assert all(pmf[k] == 0.0 for k in range(1, 6))

    def test_negative_lambda_treated_as_zero(self):
        pmf = _poisson_pmf(-1.0, max_goals=5)
        assert pmf[0] == pytest.approx(1.0)

    def test_mode_at_floor_of_lambda(self):
        # For lambda=3, mode is at k=3 (or k=2, both are valid)
        pmf = _poisson_pmf(3.0, max_goals=10)
        assert pmf[3] == max(pmf)

    def test_length_is_max_goals_plus_one(self):
        pmf = _poisson_pmf(2.0, max_goals=7)
        assert len(pmf) == 8

    def test_known_value(self):
        # P(X=0 | lambda=1) = e^-1 ≈ 0.3679
        pmf = _poisson_pmf(1.0, max_goals=10)
        assert pmf[0] == pytest.approx(math.exp(-1.0), rel=1e-6)


class TestCalculateWinProbabilities:
    def test_probs_sum_to_one(self):
        hw, d, aw = calculate_win_probabilities(2.5, 2.5)
        assert hw + d + aw == pytest.approx(1.0, abs=1e-4)

    def test_symmetric_lambdas_equal_home_away_probs(self):
        hw, d, aw = calculate_win_probabilities(2.5, 2.5)
        # Slight asymmetry is expected from score-matrix truncation at max_goals=10
        assert hw == pytest.approx(aw, abs=3e-4)

    def test_higher_lambda_home_means_higher_home_win_prob(self):
        hw_high, _, _ = calculate_win_probabilities(3.5, 2.0)
        hw_low, _, _ = calculate_win_probabilities(2.0, 3.5)
        assert hw_high > hw_low

    def test_no_negative_probabilities(self):
        hw, d, aw = calculate_win_probabilities(1.0, 4.0)
        assert hw >= 0.0
        assert d >= 0.0
        assert aw >= 0.0

    def test_all_prob_between_zero_and_one(self):
        for lh, la in [(0.5, 0.5), (1.0, 3.0), (3.5, 1.5), (2.8, 2.8)]:
            hw, d, aw = calculate_win_probabilities(lh, la)
            assert 0.0 <= hw <= 1.0
            assert 0.0 <= d <= 1.0
            assert 0.0 <= aw <= 1.0

    def test_large_lambda_difference(self):
        hw, _, aw = calculate_win_probabilities(5.0, 1.0)
        assert hw > aw

    def test_zero_lambda_away_home_almost_always_wins(self):
        hw, d, aw = calculate_win_probabilities(2.0, 0.0)
        assert hw > 0.85
        # Tiny residual from PMF truncation at max_goals=10 (P(X>10|lam=2) ≈ 8e-6)
        assert aw < 1e-4

    def test_draw_probability_reasonable_range(self):
        _, d, _ = calculate_win_probabilities(2.8, 2.8)
        # NHL draw (OT) prob typically 15-25%
        assert 0.10 < d < 0.30


class TestExpectedGoalsDistribution:
    def test_returns_goal_distribution(self):
        dist = expected_goals_distribution(2.5)
        assert isinstance(dist, GoalDistribution)
        assert dist.lam == 2.5

    def test_probs_length(self):
        dist = expected_goals_distribution(2.5, max_goals=8)
        assert len(dist.probs) == 9

    def test_probs_sum_to_one(self):
        dist = expected_goals_distribution(2.0, max_goals=20)
        assert abs(sum(dist.probs) - 1.0) < 1e-5
