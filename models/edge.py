"""
Betting edge computation and game selection.

Compares Poisson model probabilities against market-implied probabilities to
compute the edge (model − market). Selects the featured game as the one with
the largest composite divergence score across today's slate.
"""

from __future__ import annotations

from dataclasses import dataclass

from data.odds import GameOdds
from models.team_model import PoissonResult


@dataclass
class BettingEdge:
    game_id: str
    home_team: str
    away_team: str
    model_home_win_prob: float
    market_home_implied_prob: float
    moneyline_edge: float       # model − market; positive = model likes home
    model_expected_total: float
    market_total_line: float | None
    total_edge: float           # model total − market line; positive = model expects more goals
    divergence_score: float     # composite ranking metric (higher = more interesting)
    featured: bool = False


def compute_edge(result: PoissonResult, odds: GameOdds) -> BettingEdge:
    """Compute the model/market divergence for a single game."""
    ml_edge = result.home_win_prob - odds.home_implied_prob
    total_edge = (
        result.expected_total - odds.total_line
        if odds.total_line is not None
        else 0.0
    )
    # Moneyline edge weighted more than totals edge
    divergence = abs(ml_edge) * 1.5 + abs(total_edge) * 0.5

    return BettingEdge(
        game_id=odds.game_id,
        home_team=result.home_team,
        away_team=result.away_team,
        model_home_win_prob=round(result.home_win_prob, 4),
        market_home_implied_prob=round(odds.home_implied_prob, 4),
        moneyline_edge=round(ml_edge, 4),
        model_expected_total=round(result.expected_total, 3),
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
