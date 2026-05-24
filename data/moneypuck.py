"""
MoneyPuck CSV fetcher.

Re-fetches on every call (free, no rate-limit risk).
Uses regular-season data even during playoffs — larger sample, more stable.

Column names verified against MoneyPuck export as of 2025-26 season.
If columns change, update the _parse_* functions below.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

MONEYPUCK_BASE = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
_REQUEST_TIMEOUT = 20


@dataclass
class TeamStats:
    team: str
    xgf_per_game: float     # expected goals for per game
    xga_per_game: float     # expected goals against per game
    shot_rate_60: float     # shots on goal for per 60 min
    save_pct: float         # 1 - (goals_against / shots_against)
    pp_pct: float           # power play %  (0.0 if unavailable)
    pk_pct: float           # penalty kill % (0.0 if unavailable)
    games_played: int


@dataclass
class PlayerStats:
    player_id: str
    player_name: str
    team: str
    position: str           # "C", "L", "R", "D", "G"
    shots_per_60: float     # individual shots on goal per 60 min
    shooting_pct: float     # goals / shots on goal
    toi_per_game: float     # average time on ice in minutes
    games_played: int


def fetch_team_stats(season: str | None = None) -> dict[str, TeamStats]:
    """Return {team_abbrev: TeamStats} for all teams, using 'all' situation."""
    season = season or _current_season_year()
    url = f"{MONEYPUCK_BASE}/{season}/regular/teams.csv"
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return _parse_teams(resp.text)


def fetch_player_stats(
    season: str | None = None,
    team: str | None = None,
) -> list[PlayerStats]:
    """Return all skaters; optionally filter to one team."""
    season = season or _current_season_year()
    url = f"{MONEYPUCK_BASE}/{season}/regular/skaters.csv"
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return _parse_skaters(resp.text, team_filter=team)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_teams(csv_text: str) -> dict[str, TeamStats]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    all_rows = {r["team"]: r for r in rows if r.get("situation") == "all"}

    result: dict[str, TeamStats] = {}
    for team, r in all_rows.items():
        gp = max(1, int(float(r.get("gamesPlayed", 1) or 1)))
        ice_secs = float(r.get("iceTime", gp * 3600) or gp * 3600)
        ice_hours = ice_secs / 3600

        shots_for = float(r.get("shotsOnGoalFor", 0) or 0)
        shots_against = float(r.get("shotsOnGoalAgainst", 0) or 0)
        goals_against = float(r.get("goalsAgainst", 0) or 0)
        xgf = float(r.get("xGoalsFor", 0) or 0)
        xga = float(r.get("xGoalsAgainst", 0) or 0)

        save_pct = (
            1.0 - goals_against / shots_against
            if shots_against > 0
            else 0.910
        )
        shot_rate_60 = shots_for / ice_hours if ice_hours > 0 else 30.0

        result[team] = TeamStats(
            team=team,
            xgf_per_game=xgf / gp,
            xga_per_game=xga / gp,
            shot_rate_60=shot_rate_60,
            save_pct=round(save_pct, 4),
            pp_pct=_safe_float(r.get("powerPlayPct")),
            pk_pct=_safe_float(r.get("penaltyKillPct")),
            games_played=gp,
        )
    return result


def _parse_skaters(csv_text: str, team_filter: str | None) -> list[PlayerStats]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    players: list[PlayerStats] = []

    for r in rows:
        if r.get("situation") != "all":
            continue
        if team_filter and r.get("team") != team_filter:
            continue

        gp = max(1, int(float(r.get("games_played", 1) or 1)))
        ice_secs = float(r.get("icetime", 0) or 0)
        ice_hours = ice_secs / 3600
        toi_per_game = (ice_secs / gp / 60) if gp > 0 else 0.0

        shots = float(r.get("I_F_shotsOnGoal", 0) or 0)
        goals = float(r.get("I_F_goals", 0) or 0)
        shots_per_60 = shots / ice_hours if ice_hours > 0 else 0.0
        shooting_pct = goals / shots if shots > 0 else 0.0

        players.append(PlayerStats(
            player_id=r.get("playerId", ""),
            player_name=r.get("name", ""),
            team=r.get("team", ""),
            position=r.get("position", ""),
            shots_per_60=round(shots_per_60, 4),
            shooting_pct=round(shooting_pct, 4),
            toi_per_game=round(toi_per_game, 2),
            games_played=gp,
        ))
    return players


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val: str | None) -> float:
    try:
        return float(val) if val else 0.0
    except (ValueError, TypeError):
        return 0.0


def _current_season_year() -> str:
    now = datetime.now(timezone.utc)
    year = now.year if now.month >= 10 else now.year - 1
    return str(year)
