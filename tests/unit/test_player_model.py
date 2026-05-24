"""Unit tests for player_model.py."""

import pytest

from data.moneypuck import PlayerStats
from models.player_model import (
    PlayerPoissonResult,
    _player_lambda,
    run_player_model,
    top_goal_scorers,
)


class TestPlayerLambda:
    def test_zero_toi_returns_zero(self, sample_player):
        from data.moneypuck import PlayerStats
        no_ice = PlayerStats(
            player_id="x", player_name="X", team="BOS", position="C",
            shots_per_60=3.0, shooting_pct=0.12, toi_per_game=0.0,
            games_played=50,
        )
        assert _player_lambda(no_ice, 1.0) == 0.0

    def test_zero_shooting_pct_returns_zero(self, sample_player):
        from data.moneypuck import PlayerStats
        no_shoot = PlayerStats(
            player_id="x", player_name="X", team="BOS", position="C",
            shots_per_60=3.0, shooting_pct=0.0, toi_per_game=18.0,
            games_played=50,
        )
        assert _player_lambda(no_shoot, 1.0) == 0.0

    def test_multiplier_scales_lambda(self, sample_player):
        lam_1x = _player_lambda(sample_player, 1.0)
        lam_2x = _player_lambda(sample_player, 2.0)
        assert lam_2x == pytest.approx(lam_1x * 2.0, rel=1e-6)

    def test_known_calculation(self):
        # shots_per_60=4.0, toi_per_game=20.0 → shots_per_game = 4.0*(20/60) = 1.333
        # shooting_pct=0.15 → lambda = 1.333 * 0.15 = 0.2
        p = PlayerStats(
            player_id="x", player_name="X", team="Y", position="C",
            shots_per_60=4.0, shooting_pct=0.15, toi_per_game=20.0,
            games_played=60,
        )
        assert _player_lambda(p, 1.0) == pytest.approx(0.2, rel=1e-4)


class TestRunPlayerModel:
    def test_returns_player_poisson_result(self, sample_player):
        result = run_player_model(sample_player)
        assert isinstance(result, PlayerPoissonResult)

    def test_goal_prob_between_zero_and_one(self, sample_player):
        result = run_player_model(sample_player)
        assert 0.0 <= result.goal_prob <= 1.0

    def test_two_goal_prob_less_than_goal_prob(self, sample_player):
        result = run_player_model(sample_player)
        assert result.two_goal_prob <= result.goal_prob

    def test_player_name_preserved(self, sample_player):
        result = run_player_model(sample_player)
        assert result.player_name == "David Pastrnak"

    def test_team_preserved(self, sample_player):
        result = run_player_model(sample_player)
        assert result.team == "BOS"

    def test_calibration_version_set(self, sample_player):
        result = run_player_model(sample_player)
        assert result.calibration_version == "uncalibrated_v0"

    def test_high_shooter_has_higher_goal_prob(self):
        base = PlayerStats(
            player_id="a", player_name="A", team="X", position="C",
            shots_per_60=2.0, shooting_pct=0.10, toi_per_game=18.0, games_played=60,
        )
        elite = PlayerStats(
            player_id="b", player_name="B", team="X", position="C",
            shots_per_60=5.0, shooting_pct=0.18, toi_per_game=22.0, games_played=60,
        )
        assert run_player_model(elite).goal_prob > run_player_model(base).goal_prob


class TestTopGoalScorers:
    def _make_players(self):
        return [
            PlayerStats("1", "Player A", "BOS", "C", 4.0, 0.15, 20.0, 60),
            PlayerStats("2", "Player B", "BOS", "L", 3.0, 0.12, 18.0, 60),
            PlayerStats("3", "Player C", "BOS", "R", 5.0, 0.18, 19.0, 60),
            PlayerStats("4", "Player D", "BOS", "D", 2.0, 0.08, 24.0, 60),  # defender, excluded
            PlayerStats("5", "Player E", "FLA", "C", 4.5, 0.16, 20.0, 60),  # wrong team
            PlayerStats("6", "Player F", "BOS", "C", 1.0, 0.05, 10.0, 5),   # too few games
        ]

    def test_returns_correct_count(self):
        results = top_goal_scorers(self._make_players(), "BOS", top_n=2)
        assert len(results) == 2

    def test_excludes_defenders(self):
        results = top_goal_scorers(self._make_players(), "BOS", top_n=5)
        assert all(r.team == "BOS" for r in results)
        # Player D (defender) should not be in results
        names = [r.player_name for r in results]
        assert "Player D" not in names

    def test_excludes_wrong_team(self):
        results = top_goal_scorers(self._make_players(), "BOS", top_n=5)
        assert all(r.team == "BOS" for r in results)
        names = [r.player_name for r in results]
        assert "Player E" not in names

    def test_sorted_by_expected_goals_descending(self):
        results = top_goal_scorers(self._make_players(), "BOS", top_n=3)
        for i in range(len(results) - 1):
            assert results[i].expected_goals >= results[i + 1].expected_goals

    def test_empty_when_no_team_players(self):
        results = top_goal_scorers(self._make_players(), "NYR", top_n=3)
        assert results == []
