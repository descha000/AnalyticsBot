"""
Team-level Poisson model.

Converts TeamStats from MoneyPuck into expected-goals lambdas using a
Dixon-Coles-style attack/defence adjustment, then delegates to poisson.py
for the probability computation.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.moneypuck import TeamStats
from models.calibration.historical import get_calibration_factors
from models.poisson import calculate_win_probabilities

# League-average xGF per game (all situations, NHL 2024-25 benchmark).
# Update if the league scoring environment shifts significantly.
_LEAGUE_AVG_XGF = 2.8


@dataclass
class PoissonResult:
    home_team: str
    away_team: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    expected_home_goals: float
    expected_away_goals: float
    expected_total: float
    calibration_version: str


def run_team_model(
    home: TeamStats,
    away: TeamStats,
    season: str | None = None,
) -> PoissonResult:
    """
    Run the Poisson model for a single game.

    Strategy:
      lambda_home = home_attack_strength × away_defence_weakness
      attack_strength  = team_xgf_per_game / league_avg
      defence_weakness = team_xga_per_game / league_avg
      → lambda = (home_xgf / avg) × (away_xga / avg) × avg
    """
    cal = get_calibration_factors(season)

    lambda_home = _estimate_lambda(home, away, cal.team_goal_multiplier)
    lambda_away = _estimate_lambda(away, home, cal.team_goal_multiplier)

    home_win, draw, away_win = calculate_win_probabilities(lambda_home, lambda_away)

    return PoissonResult(
        home_team=home.team,
        away_team=away.team,
        home_win_prob=round(home_win, 4),
        draw_prob=round(draw, 4),
        away_win_prob=round(away_win, 4),
        expected_home_goals=round(lambda_home, 3),
        expected_away_goals=round(lambda_away, 3),
        expected_total=round(lambda_home + lambda_away, 3),
        calibration_version=cal.version,
    )


def _estimate_lambda(attacking: TeamStats, defending: TeamStats, multiplier: float) -> float:
    raw = (
        (attacking.xgf_per_game / _LEAGUE_AVG_XGF)
        * (defending.xga_per_game / _LEAGUE_AVG_XGF)
        * _LEAGUE_AVG_XGF
    )
    return max(0.1, raw * multiplier)
