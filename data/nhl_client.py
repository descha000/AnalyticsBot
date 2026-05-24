"""
nhlpy (nhl-api-py) wrapper for AnalyticsBot.

Provides three data enrichments for the pre-game slot:
  - fetch_game_scratches     -> set of player IDs scratched from a game
  - fetch_goalie_save_pct    -> save% from NHL Edge for a given goalie
  - fetch_player_recent_form -> last-N-game goal/shot/point totals for a player
  - fetch_team_goalie_ids    -> goalie player IDs for a team this season

All functions return empty/None on any API failure so the pipeline degrades
gracefully — no enrichment data is better than a crash 6 h before game time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from nhlpy import NHLClient

logger = logging.getLogger(__name__)

_client: NHLClient | None = None


def _get_client() -> NHLClient:
    global _client
    if _client is None:
        _client = NHLClient()
    return _client


# ---------------------------------------------------------------------------
# Scratches
# ---------------------------------------------------------------------------

def fetch_game_scratches(game_id: str) -> set[str]:
    """Return set of player IDs (as strings) scratched from *game_id*.

    Returns empty set on any error — callers treat it as "scratches unknown"
    rather than "nobody is scratched."
    """
    try:
        data = _get_client().game_center.season_series_matchup(game_id=game_id)
        scratches = data.get("gameInfo", {}).get("scratches", [])
        return {str(s.get("playerId") or s.get("id", "")) for s in scratches if s}
    except Exception as exc:
        logger.warning("fetch_game_scratches(%s) failed: %s", game_id, exc)
        return set()


# ---------------------------------------------------------------------------
# Goalie save percentage (NHL Edge)
# ---------------------------------------------------------------------------

@dataclass
class GoalieSavePct:
    player_id: str
    overall_sv_pct: float
    high_danger_sv_pct: float | None


def fetch_goalie_save_pct(
    player_id: str | int,
    season: str = "20252026",
    game_type: int = 3,          # 3 = playoffs
) -> GoalieSavePct | None:
    """Return NHL Edge save% data for a goalie. Returns None on failure."""
    try:
        data = _get_client().edge.goalie_save_percentage_detail(
            player_id=str(player_id),
            season=season,
            game_type=game_type,
        )
        overall = data.get("overallSavePctg")
        hd = data.get("highDangerSavePctg")
        if overall is None:
            return None
        return GoalieSavePct(
            player_id=str(player_id),
            overall_sv_pct=float(overall),
            high_danger_sv_pct=float(hd) if hd is not None else None,
        )
    except Exception as exc:
        logger.warning("fetch_goalie_save_pct(%s) failed: %s", player_id, exc)
        return None


# ---------------------------------------------------------------------------
# Player recent form
# ---------------------------------------------------------------------------

@dataclass
class PlayerRecentForm:
    player_id: str
    games_played: int
    goals: int
    assists: int
    points: int
    shots: int
    goals_per_game: float


def fetch_player_recent_form(
    player_id: str | int,
    season: str = "20252026",
    game_type: int = 3,
    last_n: int = 5,
) -> PlayerRecentForm | None:
    """Return goal/shot/point totals over the last *last_n* games. Returns None on failure."""
    try:
        logs = _get_client().stats.player_game_log(
            player_id=str(player_id),
            season_id=season,
            game_type=game_type,
        )
        if not logs:
            return None

        recent = logs[:last_n]
        goals = sum(int(g.get("goals", 0)) for g in recent)
        assists = sum(int(g.get("assists", 0)) for g in recent)
        shots = sum(int(g.get("shots", 0)) for g in recent)
        n = len(recent)

        return PlayerRecentForm(
            player_id=str(player_id),
            games_played=n,
            goals=goals,
            assists=assists,
            points=goals + assists,
            shots=shots,
            goals_per_game=round(goals / n, 2) if n else 0.0,
        )
    except Exception as exc:
        logger.warning("fetch_player_recent_form(%s) failed: %s", player_id, exc)
        return None


# ---------------------------------------------------------------------------
# Team roster helpers
# ---------------------------------------------------------------------------

def fetch_team_goalie_ids(team_abbr: str, season: str = "20252026") -> list[str]:
    """Return goalie player IDs for *team_abbr* this *season*. Returns [] on failure."""
    try:
        roster = _get_client().teams.team_roster(team_abbr=team_abbr, season=season)
        goalies = roster.get("goalies", [])
        return [str(g["id"]) for g in goalies if "id" in g]
    except Exception as exc:
        logger.warning("fetch_team_goalie_ids(%s) failed: %s", team_abbr, exc)
        return []
