"""
NHL public API client (api-web.nhle.com). No API key required.

Fetches today's game schedule, upcoming games, and final scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

NHL_API_BASE = "https://api-web.nhle.com/v1"
ESTIMATED_GAME_DURATION = timedelta(hours=2, minutes=45)
_REQUEST_TIMEOUT = 10


@dataclass
class NHLGame:
    game_id: str
    home_team: str          # 3-letter NHL abbrev, e.g. "BOS"
    away_team: str
    start_time_utc: datetime
    estimated_end_utc: datetime
    season: str             # e.g. "20252026"
    game_type: str          # "regular" | "playoff"


@dataclass
class GameResult:
    game_id: str
    home_score: int
    away_score: int
    went_to_ot: bool
    final_period: str       # "REG" | "OT" | "SO"


def fetch_games_on_date(date: str) -> list[NHLGame]:
    """Return all NHL games scheduled on *date* (YYYY-MM-DD)."""
    url = f"{NHL_API_BASE}/schedule/{date}"
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return _parse_schedule(resp.json(), date)


def fetch_today_games() -> list[NHLGame]:
    today = _today_str()
    return fetch_games_on_date(today)


def fetch_next_game() -> NHLGame | None:
    """Return the first NHL game found within the next 7 days, or None."""
    for days_ahead in range(1, 8):
        date = (_utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        games = fetch_games_on_date(date)
        if games:
            return games[0]
    return None


def fetch_game_result(game_id: str) -> GameResult | None:
    """Return final score for *game_id*, or None if not yet final."""
    url = f"{NHL_API_BASE}/gamecenter/{game_id}/boxscore"
    resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _parse_result(resp.json(), game_id)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_schedule(data: dict, target_date: str) -> list[NHLGame]:
    games: list[NHLGame] = []
    for day in data.get("gameWeek", []):
        if day.get("date") != target_date:
            continue
        for g in day.get("games", []):
            start = datetime.fromisoformat(
                g["startTimeUTC"].replace("Z", "+00:00")
            )
            season = str(g.get("season", _current_season()))
            game_type = "playoff" if g.get("gameType") == 3 else "regular"
            games.append(NHLGame(
                game_id=str(g["id"]),
                home_team=g["homeTeam"]["abbrev"],
                away_team=g["awayTeam"]["abbrev"],
                start_time_utc=start,
                estimated_end_utc=start + ESTIMATED_GAME_DURATION,
                season=season,
                game_type=game_type,
            ))
    return games


def _parse_result(data: dict, game_id: str) -> GameResult | None:
    if data.get("gameState") not in ("OFF", "FINAL"):
        return None
    period = data.get("periodDescriptor", {})
    period_type = period.get("periodType", "REG")
    return GameResult(
        game_id=game_id,
        home_score=int(data["homeTeam"].get("score", 0)),
        away_score=int(data["awayTeam"].get("score", 0)),
        went_to_ot=period_type in ("OT", "SO"),
        final_period=period_type,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today_str() -> str:
    return _utcnow().strftime("%Y-%m-%d")


def _current_season() -> str:
    now = _utcnow()
    year = now.year if now.month >= 10 else now.year - 1
    return f"{year}{year + 1}"
