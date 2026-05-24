"""
Poisson Goals Model
-------------------
Takes team shot rates and goalie save percentages as inputs.
Outputs win probabilities, score distributions, and betting edge vs market.

NOTE: This is a calculator, not a trained model. Lambdas are derived from
empirical inputs (shots, save %). Calibration against historical data is
a future enhancement — see CLAUDE.md for roadmap.

Integration note
----------------
The public interface used by team_model.py and player_model.py:
  - TeamInputs, MarketOdds, ModelOutput  (user's dataclasses)
  - run()                                (user's main entry point)
  - _poisson_pmf_list()                  (adapter: list PMF for player_model.py)
  - calculate_win_probabilities()        (adapter: (λ_h, λ_a) → tuple for tests)

To drop in a calibrated version: replace the body of run() or adjust the
lambdas before calling run(). The dataclass signatures must not change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Optional


@dataclass
class TeamInputs:
    name: str
    shots_for_pg: float         # Avg shots on goal per game (offense)
    opp_goalie_sv_pct: float    # Opponent goalie's relevant save % (ECF career, vs this team, etc.)


@dataclass
class MarketOdds:
    home_ml: int    # American moneyline, e.g. -220
    away_ml: int    # American moneyline, e.g. +185
    total: float    # Over/under line, e.g. 5.5


@dataclass
class ModelOutput:
    home_name: str
    away_name: str
    lambda_home: float
    lambda_away: float
    p_home_win: float
    p_away_win: float
    p_ot: float
    expected_total: float
    p_over: float
    p_under: float
    # Betting edge (only populated if market odds provided)
    home_market_implied: Optional[float] = None
    away_market_implied: Optional[float] = None
    home_edge_pp: Optional[float] = None    # percentage points vs market
    away_edge_pp: Optional[float] = None
    top_scores: Optional[list] = None       # [(home_goals, away_goals, probability)]


MAX_GOALS = 9           # 0–8 goals per team covers 99.9%+ of outcomes
HOME_OT_WIN_RATE = 0.53 # Slight home-ice advantage in OT


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for Poisson distribution with rate lambda."""
    return (lam ** k * math.exp(-lam)) / math.factorial(k)


def _remove_vig(home_implied: float, away_implied: float) -> tuple[float, float]:
    """Strip the bookmaker's margin from implied probabilities."""
    total = home_implied + away_implied
    return home_implied / total, away_implied / total


def _american_to_implied(ml: int) -> float:
    """Convert American moneyline to raw implied probability (with vig)."""
    if ml < 0:
        return abs(ml) / (abs(ml) + 100)
    return 100 / (ml + 100)


def run(home: TeamInputs, away: TeamInputs,
        odds: Optional[MarketOdds] = None,
        total_line: Optional[float] = None) -> ModelOutput:
    """
    Run the Poisson model for a single game.

    Parameters
    ----------
    home, away : TeamInputs
        Shot rates and opponent goalie save %.
    odds : MarketOdds, optional
        If provided, computes betting edge vs market.
    total_line : float, optional
        Override the total line from odds (e.g. 5.5).

    Returns
    -------
    ModelOutput
        Full probability output and betting signals.
    """
    # Expected goals = shots × (1 - save_pct)
    lam_home = home.shots_for_pg * (1 - away.opp_goalie_sv_pct)
    lam_away = away.shots_for_pg * (1 - home.opp_goalie_sv_pct)

    # Build full score distribution
    score_dist: dict[tuple[int, int], float] = {}
    for h, a in product(range(MAX_GOALS), range(MAX_GOALS)):
        score_dist[(h, a)] = _poisson_pmf(h, lam_home) * _poisson_pmf(a, lam_away)

    # Regulation + OT outcomes
    p_home_reg = sum(p for (h, a), p in score_dist.items() if h > a)
    p_away_reg = sum(p for (h, a), p in score_dist.items() if a > h)
    p_ot       = sum(p for (h, a), p in score_dist.items() if h == a)

    p_home_total = p_home_reg + p_ot * HOME_OT_WIN_RATE
    p_away_total = p_away_reg + p_ot * (1 - HOME_OT_WIN_RATE)
    norm = p_home_total + p_away_total
    p_home_norm = p_home_total / norm
    p_away_norm = p_away_total / norm

    # Over/under
    line = total_line or (odds.total if odds else 5.5)
    p_over  = sum(p for (h, a), p in score_dist.items() if h + a > line)
    p_under = sum(p for (h, a), p in score_dist.items() if h + a < line)

    # Top 5 most likely exact scores
    top_scores = [
        (h, a, round(p * 100, 1))
        for (h, a), p in sorted(score_dist.items(), key=lambda x: -x[1])[:5]
    ]

    # Betting edge
    home_impl = away_impl = home_edge = away_edge = None
    if odds:
        raw_home = _american_to_implied(odds.home_ml)
        raw_away = _american_to_implied(odds.away_ml)
        home_impl, away_impl = _remove_vig(raw_home, raw_away)
        home_edge = round((p_home_norm - home_impl) * 100, 1)
        away_edge = round((p_away_norm - away_impl) * 100, 1)

    return ModelOutput(
        home_name=home.name,
        away_name=away.name,
        lambda_home=round(lam_home, 2),
        lambda_away=round(lam_away, 2),
        p_home_win=round(p_home_norm * 100, 1),
        p_away_win=round(p_away_norm * 100, 1),
        p_ot=round(p_ot * 100, 1),
        expected_total=round(lam_home + lam_away, 2),
        p_over=round(p_over * 100, 1),
        p_under=round(p_under * 100, 1),
        home_market_implied=round(home_impl * 100, 1) if home_impl else None,
        away_market_implied=round(away_impl * 100, 1) if away_impl else None,
        home_edge_pp=home_edge,
        away_edge_pp=away_edge,
        top_scores=top_scores,
    )


def best_bet(output: ModelOutput) -> Optional[str]:
    """
    Return the single strongest bet signal, or None if no clear edge.
    Threshold: >8pp edge on moneyline, or >15pp on total.
    """
    edges = []
    if output.home_edge_pp and output.home_edge_pp >= 8:
        edges.append(("ML", output.home_name, output.home_edge_pp))
    if output.away_edge_pp and output.away_edge_pp >= 8:
        edges.append(("ML", output.away_name, output.away_edge_pp))

    # Total edge
    line = 5.5  # TODO: pass through from odds
    if output.p_under >= 65:
        edges.append(("UNDER", str(line), output.p_under - 50))
    if output.p_over >= 65:
        edges.append(("OVER", str(line), output.p_over - 50))

    if not edges:
        return None
    top = max(edges, key=lambda x: x[2])
    return f"{top[0]} {top[1]} (+{top[2]:.1f}pp edge)"


# ---------------------------------------------------------------------------
# Adapters for player_model.py and unit tests
# ---------------------------------------------------------------------------

def _poisson_pmf_list(lam: float, max_goals: int = 10) -> list[float]:
    """Return P(X=k) for k in 0..max_goals as a list. Used by player_model.py."""
    if lam <= 0:
        probs = [0.0] * (max_goals + 1)
        probs[0] = 1.0
        return probs
    return [_poisson_pmf(k, lam) for k in range(max_goals + 1)]


def calculate_win_probabilities(
    lambda_home: float,
    lambda_away: float,
) -> tuple[float, float, float]:
    """
    Adapter for tests and player_model — delegates to run() via synthetic TeamInputs.

    Returns (home_win_prob, ot_prob, away_win_prob) as proportions (0–1).
    Win probs are OT-adjusted (home_win + away_win ≈ 1.0).
    """
    home_inputs = TeamInputs(name="home", shots_for_pg=lambda_home, opp_goalie_sv_pct=0.0)
    away_inputs = TeamInputs(name="away", shots_for_pg=lambda_away, opp_goalie_sv_pct=0.0)
    out = run(home_inputs, away_inputs)
    return out.p_home_win / 100, out.p_ot / 100, out.p_away_win / 100
