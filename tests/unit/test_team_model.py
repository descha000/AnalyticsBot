"""Unit tests for team_model.py."""

import pytest

from models.team_model import PoissonResult, run_team_model


class TestRunTeamModel:
    def test_returns_poisson_result(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert isinstance(result, PoissonResult)

    def test_win_probabilities_sum_to_one(self, boston_stats, florida_stats):
        # home_win_prob + away_win_prob = 1.0 (OT-adjusted, normalized).
        # draw_prob = raw OT probability — bonus info, not a third exclusive outcome.
        result = run_team_model(boston_stats, florida_stats)
        assert result.home_win_prob + result.away_win_prob == pytest.approx(1.0, abs=1e-3)

    def test_home_team_label_correct(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert result.home_team == "BOS"
        assert result.away_team == "FLA"

    def test_expected_total_is_sum_of_lambdas(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        assert result.expected_total == pytest.approx(
            result.expected_home_goals + result.expected_away_goals, abs=0.001
        )

    def test_calibration_version_regular(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats, game_type="regular")
        assert result.calibration_version == "uncalibrated_v0"

    def test_calibration_version_playoff(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats, game_type="playoff")
        assert result.calibration_version == "playoff_empirical_v0"

    def test_playoff_expected_total_lower_than_regular(self, boston_stats, florida_stats):
        reg = run_team_model(boston_stats, florida_stats, game_type="regular")
        plo = run_team_model(boston_stats, florida_stats, game_type="playoff")
        assert plo.expected_total < reg.expected_total
        assert plo.expected_total == pytest.approx(reg.expected_total * 0.90, rel=0.01)

    def test_stronger_offense_higher_win_prob(self, boston_stats, florida_stats):
        from data.moneypuck import TeamStats
        strong = TeamStats(
            team="STR", xgf_per_game=3.2, xga_per_game=2.4,
            shot_rate_60=36.0, save_pct=0.920, pp_pct=0.24, pk_pct=0.84,
            games_played=82,
        )
        weak = TeamStats(
            team="WEK", xgf_per_game=2.4, xga_per_game=3.0,
            shot_rate_60=26.0, save_pct=0.895, pp_pct=0.17, pk_pct=0.79,
            games_played=82,
        )
        result = run_team_model(strong, weak)
        assert result.home_win_prob > result.away_win_prob

    def test_symmetric_teams_near_equal_win_prob(self, boston_stats):
        from data.moneypuck import TeamStats
        clone = TeamStats(
            team="CLN", xgf_per_game=boston_stats.xgf_per_game,
            xga_per_game=boston_stats.xga_per_game,
            shot_rate_60=boston_stats.shot_rate_60,
            save_pct=boston_stats.save_pct,
            pp_pct=boston_stats.pp_pct, pk_pct=boston_stats.pk_pct,
            games_played=boston_stats.games_played,
        )
        result = run_team_model(boston_stats, clone)
        assert result.home_win_prob == pytest.approx(result.away_win_prob, abs=0.05)

    def test_all_probs_between_zero_and_one(self, boston_stats, florida_stats):
        result = run_team_model(boston_stats, florida_stats)
        for p in (result.home_win_prob, result.draw_prob, result.away_win_prob):
            assert 0.0 <= p <= 1.0

    def test_lambda_uses_shots_and_save_pct(self, boston_stats, florida_stats):
        # lambda_home = boston.shot_rate_60 * (1 - florida.save_pct)
        result = run_team_model(boston_stats, florida_stats)
        expected_lh = boston_stats.shot_rate_60 * (1 - florida_stats.save_pct)
        assert result.expected_home_goals == pytest.approx(expected_lh, rel=0.01)
