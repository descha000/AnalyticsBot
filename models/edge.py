"""
Betting edge computation and game selection.

Compares Poisson model probabilities against market-implied probabilities to
compute the edge (model − market). Selects the featured game as the one with
the largest composite divergence score across today's slate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from data.odds import GameOdds
from models.team_model import PoissonResult


@dataclass
class BettingEdge:
    game_id: str
    home_team: str
    away_team: str
    model_home_win_prob: float
    model_expected_total: float
    has_odds: bool                              # False = no market data available yet
    market_home_implied_prob: Optional[float]   # None when has_odds=False
    moneyline_edge: Optional[float]             # None when has_odds=False
    market_total_line: Optional[float]          # None when has_odds=False
    total_edge: Optional[float]                 # None when has_odds=False
    divergence_score: float                     # 0.0 when has_odds=False
    featured: bool = False


def compute_edge(result: PoissonResult, odds: Optional[GameOdds]) -> BettingEdge:
    """Compute the model/market divergence. When odds is None, returns model-only edge."""
    if odds is None:
        return BettingEdge(
            game_id=result.home_team + "_" + result.away_team,
            home_team=result.home_team,
            away_team=result.away_team,
            model_home_win_prob=round(result.home_win_prob, 4),
            model_expected_total=round(result.expected_total, 3),
            has_odds=False,
            market_home_implied_prob=None,
            moneyline_edge=None,
            market_total_line=None,
            total_edge=None,
            divergence_score=0.0,
        )

    ml_edge = result.home_win_prob - odds.home_implied_prob
    total_edge = (
        result.expected_total - odds.total_line
        if odds.total_line is not None
        else 0.0
    )
    divergence = abs(ml_edge) * 1.5 + abs(total_edge) * 0.5

    return BettingEdge(
        game_id=odds.game_id,
        home_team=result.home_team,
        away_team=result.away_team,
        model_home_win_prob=round(result.home_win_prob, 4),
        model_expected_total=round(result.expected_total, 3),
        has_odds=True,
        market_home_implied_prob=round(odds.home_implied_prob, 4),
        moneyline_edge=round(ml_edge, 4),
        market_total_line=odds.total_line,
        total_edge=round(total_edge, 3),
        divergence_score=round(divergence, 4),
    )


def select_featured_game(edges: list[BettingEdge]) -> BettingEdge | None:
    """Return the game with the highest divergence_score and mark it featured."""
    if not edges:
        return None
    edges_sorted = sorted(edges, key=lambda e: e.divergence_score, reverse=True)
    winner = edges_sorted[0]
    winner.featured = True
    return winner
