"""
Team-level Poisson model.

Converts TeamStats from MoneyPuck into expected-goals lambdas using the
user's formula (shots × (1 - save_pct)), then delegates to poisson.py
for the full probability computation.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.moneypuck import TeamStats
from models.calibration.historical import get_calibration_factors
from models.poisson import ModelOutput, TeamInputs
from models.poisson import run as poisson_run


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
    game_type: str = "regular",
    home_starter_sv_pct: float | None = None,
    away_starter_sv_pct: float | None = None,
) -> PoissonResult:
    """
    Run the Poisson model for a single game.

    Lambda = team_shot_rate_60 × (1 - opponent_goalie_sv_pct) × calibration_multiplier.
    game_type: "regular" | "playoff" — playoffs apply a 0.90 calibration factor.

    home_starter_sv_pct / away_starter_sv_pct: live NHL Edge save% for each team's
    starting goalie. When provided, these replace the MoneyPuck season-average save_pct.
    """
    cal = get_calibration_factors(season, game_type)

    # opp_goalie_sv_pct = THIS team's own goalie (who faces incoming shots).
    # lam_home = home.shots * (1 - away.opp_goalie_sv_pct)  → away goalie faces home shots
    # lam_away = away.shots * (1 - home.opp_goalie_sv_pct)  → home goalie faces away shots
    home_inputs = TeamInputs(
        name=home.team,
        shots_for_pg=home.shot_rate_60 * cal.team_goal_multiplier,
        opp_goalie_sv_pct=home_starter_sv_pct if home_starter_sv_pct is not None else home.save_pct,
    )
    away_inputs = TeamInputs(
        name=away.team,
        shots_for_pg=away.shot_rate_60 * cal.team_goal_multiplier,
        opp_goalie_sv_pct=away_starter_sv_pct if away_starter_sv_pct is not None else away.save_pct,
    )
    out: ModelOutput = poisson_run(home_inputs, away_inputs)

    return PoissonResult(
        home_team=home.team,
        away_team=away.team,
        home_win_prob=round(out.p_home_win / 100, 4),
        draw_prob=round(out.p_ot / 100, 4),
        away_win_prob=round(out.p_away_win / 100, 4),
        expected_home_goals=out.lambda_home,
        expected_away_goals=out.lambda_away,
        expected_total=out.expected_total,
        calibration_version=cal.version,
    )
