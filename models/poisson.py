"""
Poisson goals model.

This is the integration point for your prototype. The public interface —
calculate_win_probabilities() and expected_goals_distribution() — is used by
team_model.py and player_model.py and must not change signature.

To drop in your own implementation: replace the body of
calculate_win_probabilities() below. Everything else in this file is support
code that your implementation may use or ignore.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class GoalDistribution:
    lam: float
    probs: list[float]  # probs[k] = P(exactly k goals), k in 0..len-1


def calculate_win_probabilities(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 10,
) -> tuple[float, float, float]:
    """
    Bivariate Poisson goals model (independent marginals).

    Args:
        lambda_home: expected goals for the home team
        lambda_away: expected goals for the away team
        max_goals:   score-matrix truncation point (10 covers 99.9%+ of NHL games)

    Returns:
        (home_win_prob, draw_prob, away_win_prob)  — sums to ≈ 1.0

    --- REPLACE THIS BODY WITH YOUR PROTOTYPE ---
    The implementation below is a correct reference version; swap it out
    whenever you're ready to plug in your calibrated model.
    """
    home_pmf = _poisson_pmf(lambda_home, max_goals)
    away_pmf = _poisson_pmf(lambda_away, max_goals)

    home_win = draw = 0.0
    for i, ph in enumerate(home_pmf):
        for j, pa in enumerate(away_pmf):
            p = ph * pa
            if i > j:
                home_win += p
            elif i == j:
                draw += p

    away_win = max(0.0, 1.0 - home_win - draw)
    return home_win, draw, away_win


def expected_goals_distribution(lam: float, max_goals: int = 10) -> GoalDistribution:
    """Return the full PMF for a Poisson-distributed goal scorer with rate *lam*."""
    return GoalDistribution(lam=lam, probs=_poisson_pmf(lam, max_goals))


# ---------------------------------------------------------------------------
# Internal helpers (used by the reference implementation above)
# ---------------------------------------------------------------------------

def _poisson_pmf(lam: float, max_goals: int) -> list[float]:
    """P(X = k) for k in 0..max_goals, X ~ Poisson(lam)."""
    if lam <= 0:
        probs = [0.0] * (max_goals + 1)
        probs[0] = 1.0
        return probs
    exp_neg_lam = math.exp(-lam)
    probs = []
    power = 1.0
    factorial = 1.0
    for k in range(max_goals + 1):
        if k > 0:
            power *= lam
            factorial *= k
        probs.append(exp_neg_lam * power / factorial)
    return probs
