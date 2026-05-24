"""
Player-level Poisson model.

Converts PlayerStats from MoneyPuck into a per-game expected-goals lambda,
then uses poisson.py to compute goal probabilities for pre-game player props.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.moneypuck import PlayerStats
from models.calibration.historical import get_calibration_factors
from models.poisson import _poisson_pmf_list


@dataclass
class PlayerPoissonResult:
    player_name: str
    team: str
    expected_goals: float   # lambda — expected goals in one game
    goal_prob: float        # P(goals >= 1)
    two_goal_prob: float    # P(goals >= 2)
    calibration_version: str


def run_player_model(
    player: PlayerStats,
    season: str | None = None,
) -> PlayerPoissonResult:
    """Estimate goal probability for *player* in a single game."""
    cal = get_calibration_factors(season)
    lam = _player_lambda(player, cal.player_goal_multiplier)

    pmf = _poisson_pmf_list(lam, max_goals=5)
    goal_prob = max(0.0, 1.0 - pmf[0])
    two_goal_prob = max(0.0, 1.0 - pmf[0] - pmf[1])

    return PlayerPoissonResult(
        player_name=player.player_name,
        team=player.team,
        expected_goals=round(lam, 4),
        goal_prob=round(goal_prob, 4),
        two_goal_prob=round(two_goal_prob, 4),
        calibration_version=cal.version,
    )


def top_goal_scorers(
    players: list[PlayerStats],
    team: str,
    top_n: int = 3,
    season: str | None = None,
) -> list[PlayerPoissonResult]:
    """Return the top *top_n* goal scorers for *team*, ranked by expected_goals."""
    team_forwards = [
        p for p in players
        if p.team == team and p.position in ("C", "L", "R", "F")
        and p.games_played >= 10
    ]
    results = [run_player_model(p, season) for p in team_forwards]
    results.sort(key=lambda r: r.expected_goals, reverse=True)
    return results[:top_n]


def _player_lambda(player: PlayerStats, multiplier: float) -> float:
    """Expected goals in one game = shots_per_game × shooting_pct × calibration."""
    shots_per_game = player.shots_per_60 * (player.toi_per_game / 60.0)
    return max(0.0, shots_per_game * player.shooting_pct * multiplier)
