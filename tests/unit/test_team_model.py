"""Unit tests for team_model.py."""

import pytest

from models.team_model import PoissonResult, _estimate_lambda, run_team_model


class TestEstimateLambda:
    def test_equal_teams_returns_league_average(self, boston_stats, florida_stats):
        # When both teams are at league average xGF/xGA = 2.8,
        # lambda should equal league average
        from data.moneypuck import TeamStats
        avg = TeamStats(
            team="AVG", xgf_per_game=2.8, xga_per_game=2.8,
            shot_rate_60=30.0, save_pct=0.910, pp_pct=0.20, pk_pct=0.82,
            games_played=82,
        )
        lam = _estimate_lambda(avg, avg, multiplier=1.0)
        assert lam == pytest.approx(2.8, rel=0.01)

    def test_strong_attack_vs_weak_defence_increases_lambda(self, boston_stats, florida_stats):
        from data.moneypuck import TeamStats
        weak_defence = TeamStats(
            team="WEAK", xgf_per_game=2.0, xga_per_game=3.5,
            shot_rate_60=28.0, save_pct=0.890, pp_pct=0.18, pk_pct=0.80,
            games_played=82,
        )
        lam_vs_weak = _estimate_lambda(boston_stats, weak_defence, 1.0)
        lam_vs_strong = _estimate_lambda(boston_stats, florida_stats, 1.0)
        assert lam_vs_weak > lam_vs_strong

    def test_multiplier_scales_lambda(self, boston_stats, florida_stats):
        lam_1x = _estimate_lambda(boston_stats, florida_stats, 1.0)
        lam_2x = _estimate_lambda(boston_stats, florida_stats, 2.0)
        assert lam_2x == pytest.approx(lam_1x * 2.0, rel=1e-6)

    def test_never_returns_below_floor(self, boston_stats, florida_stats):
        from data.moneypuck import TeamStats
        zero_attack = TeamStats(
            team="X", xgf_per_game=0.0, xga_per_game=0.0,
            shot_rate_60=0.0, save_pct=0.0, pp_pct=0.0, pk_pct=0.0,
            games_played=10,
        )
        lam = _estimate_lambda(zero_attack, florida_stats, 1.0)
        assert lam >= 0.1


class TestRunTeamModel:
    def test_returns_poisson_result(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert isinstance(result, PoissonResult)

    def test_probabilities_sum_to_one(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        total = result.home_win_prob + result.draw_prob + result.away_win_prob
        assert total == pytest.approx(1.0, abs=1e-3)

    def test_home_team_label_correct(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert result.home_team == "BOS"
        assert result.away_team == "FLA"

    def test_expected_total_is_sum_of_lambdas(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert result.expected_total == pytest.approx(
            result.expected_home_goals + result.expected_away_goals, abs=0.001
        )

    def test_calibration_version_set(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert result.calibration_version == "uncalibrated_v0"

    def test_stronger_team_has_higher_win_prob(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        # Boston has higher xgf_per_game, should have higher win prob
        assert result.home_win_prob > result.away_win_prob
