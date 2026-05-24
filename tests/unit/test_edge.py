"""Unit tests for edge.py."""

import pytest

from models.edge import BettingEdge, compute_edge, select_featured_game


class TestComputeEdge:
    def test_returns_betting_edge(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        assert isinstance(result, BettingEdge)

    def test_moneyline_edge_calculation(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        expected = sample_poisson.home_win_prob - boston_odds.home_implied_prob
        assert result.moneyline_edge == pytest.approx(expected, abs=0.001)

    def test_total_edge_calculation(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        expected = sample_poisson.expected_total - boston_odds.total_line
        assert result.total_edge == pytest.approx(expected, abs=0.001)

    def test_total_edge_zero_when_no_line(self, sample_poisson, boston_odds):
        boston_odds.total_line = None
        result = compute_edge(sample_poisson, boston_odds)
        assert result.total_edge == 0.0

    def test_divergence_score_is_positive(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        assert result.divergence_score >= 0.0

    def test_game_id_preserved(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        assert result.game_id == boston_odds.game_id

    def test_team_labels_from_poisson_result(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        assert result.home_team == "BOS"
        assert result.away_team == "FLA"

    def test_featured_defaults_false(self, sample_poisson, boston_odds):
        result = compute_edge(sample_poisson, boston_odds)
        assert result.featured is False

    def test_larger_divergence_when_bigger_ml_edge(self, sample_poisson, boston_odds):
        from data.odds import GameOdds
        from models.team_model import PoissonResult

        small_edge_poisson = PoissonResult(
            "BOS", "FLA", 0.548, 0.18, 0.272, 2.9, 2.5, 5.4, "uncalibrated_v0"
        )
        big_edge_poisson = PoissonResult(
            "BOS", "FLA", 0.70, 0.15, 0.15, 2.9, 2.5, 5.4, "uncalibrated_v0"
        )
        small = compute_edge(small_edge_poisson, boston_odds)
        big = compute_edge(big_edge_poisson, boston_odds)
        assert big.divergence_score > small.divergence_score


class TestSelectFeaturedGame:
    def test_returns_none_for_empty_list(self):
        assert select_featured_game([]) is None

    def test_returns_single_edge(self, sample_edge):
        result = select_featured_game([sample_edge])
        assert result is sample_edge

    def test_marks_winner_as_featured(self, sample_edge):
        result = select_featured_game([sample_edge])
        assert result.featured is True

    def test_selects_max_divergence(self, sample_poisson, boston_odds):
        from data.odds import GameOdds
        from models.team_model import PoissonResult

        low_poisson = PoissonResult(
            "NYR", "MTL", 0.52, 0.18, 0.30, 2.8, 2.5, 5.3, "uncalibrated_v0"
        )
        low_odds = GameOdds(
            game_id="999", odds_event_id="e2", home_team="NYR", away_team="MTL",
            home_moneyline=-110, away_moneyline=-110,
            home_implied_prob=0.5238, away_implied_prob=0.4762,
            total_line=5.5, book="draftkings",
        )
        low_edge = compute_edge(low_poisson, low_odds)

        high_poisson = PoissonResult(
            "BOS", "FLA", 0.68, 0.15, 0.17, 2.9, 2.5, 5.4, "uncalibrated_v0"
        )
        high_edge = compute_edge(high_poisson, boston_odds)

        winner = select_featured_game([low_edge, high_edge])
        assert winner is high_edge
        assert winner.featured is True
        assert not low_edge.featured
