"""
The Odds API client.

Fetches moneyline (h2h) + totals for team games, and anytime goal scorer
player props. Uses American odds format throughout.

Free tier: 500 requests/month. Each call to fetch_game_odds costs 1 request;
fetch_player_odds costs 1 request per event.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
_REQUEST_TIMEOUT = 10

# Maps NHL API 3-letter abbreviations → The Odds API full team names
NHL_TEAM_NAMES: dict[str, str] = {
    "ANA": "Anaheim Ducks",
    "BOS": "Boston Bruins",
    "BUF": "Buffalo Sabres",
    "CGY": "Calgary Flames",
    "CAR": "Carolina Hurricanes",
    "CHI": "Chicago Blackhawks",
    "COL": "Colorado Avalanche",
    "CBJ": "Columbus Blue Jackets",
    "DAL": "Dallas Stars",
    "DET": "Detroit Red Wings",
    "EDM": "Edmonton Oilers",
    "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings",
    "MIN": "Minnesota Wild",
    "MTL": "Montreal Canadiens",
    "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils",
    "NYI": "New York Islanders",
    "NYR": "New York Rangers",
    "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers",
    "PIT": "Pittsburgh Penguins",
    "SJS": "San Jose Sharks",
    "SEA": "Seattle Kraken",
    "STL": "St. Louis Blues",
    "TBL": "Tampa Bay Lightning",
    "TOR": "Toronto Maple Leafs",
    "UTA": "Utah Hockey Club",
    "VAN": "Vancouver Canucks",
    "VGK": "Vegas Golden Knights",
    "WSH": "Washington Capitals",
    "WPG": "Winnipeg Jets",
}

_TEAM_NAME_TO_ABBREV: dict[str, str] = {v: k for k, v in NHL_TEAM_NAMES.items()}


@dataclass
class GameOdds:
    game_id: str            # NHL game_id (populated by match_odds_to_games)
    odds_event_id: str      # The Odds API event id
    home_team: str          # NHL abbrev
    away_team: str
    home_moneyline: int     # American odds, e.g. -145
    away_moneyline: int
    home_implied_prob: float    # devigged
    away_implied_prob: float
    total_line: float | None
    book: str               # first bookmaker used


@dataclass
class PlayerOdds:
    player_name: str
    game_id: str
    goal_line: float = 0.5
    over_price: int = 0
    implied_prob: float = 0.0
    book: str = ""


def fetch_game_odds(sport: str = "icehockey_nhl") -> list[GameOdds]:
    """Fetch moneyline + totals for all upcoming games in *sport*."""
    resp = requests.get(
        f"{ODDS_API_BASE}/sports/{sport}/odds/",
        params={
            "apiKey": _api_key(),
            "regions": "us",
            "markets": "h2h,totals",
            "oddsFormat": "american",
        },
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_game_odds(resp.json())


def match_odds_to_games(games: list, odds_list: list[GameOdds]) -> dict[str, GameOdds]:
    """Match GameOdds to NHLGame by team abbrevs. Returns {game_id: GameOdds}."""
    result: dict[str, GameOdds] = {}
    for game in games:
        for odds in odds_list:
            if odds.home_team == game.home_team and odds.away_team == game.away_team:
                odds.game_id = game.game_id
                result[game.game_id] = odds
                break
    return result


def fetch_player_odds(
    event_id: str,
    game_id: str,
    sport: str = "icehockey_nhl",
) -> list[PlayerOdds]:
    """Fetch anytime goal scorer props for a specific event."""
    resp = requests.get(
        f"{ODDS_API_BASE}/sports/{sport}/events/{event_id}/odds",
        params={
            "apiKey": _api_key(),
            "regions": "us",
            "markets": "player_goal_scorer_anytime",
            "oddsFormat": "american",
        },
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_player_odds(resp.json(), game_id)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_game_odds(events: list[dict]) -> list[GameOdds]:
    results: list[GameOdds] = []
    for event in events:
        home_full = event.get("home_team", "")
        away_full = event.get("away_team", "")
        home_abbrev = _TEAM_NAME_TO_ABBREV.get(home_full, home_full)
        away_abbrev = _TEAM_NAME_TO_ABBREV.get(away_full, away_full)

        home_ml = away_ml = 0
        total_line: float | None = None
        book_name = ""

        for bookmaker in event.get("bookmakers", []):
            book_name = bookmaker.get("key", "")
            for market in bookmaker.get("markets", []):
                if market["key"] == "h2h":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == home_full:
                            home_ml = int(outcome["price"])
                        elif outcome["name"] == away_full:
                            away_ml = int(outcome["price"])
                elif market["key"] == "totals":
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == "Over":
                            total_line = float(outcome["point"])
            break  # first bookmaker only

        if home_ml == 0 or away_ml == 0:
            continue

        home_prob, away_prob = _devig(
            _american_to_raw_prob(home_ml),
            _american_to_raw_prob(away_ml),
        )
        results.append(GameOdds(
            game_id="",
            odds_event_id=event.get("id", ""),
            home_team=home_abbrev,
            away_team=away_abbrev,
            home_moneyline=home_ml,
            away_moneyline=away_ml,
            home_implied_prob=round(home_prob, 4),
            away_implied_prob=round(away_prob, 4),
            total_line=total_line,
            book=book_name,
        ))
    return results


def _parse_player_odds(data: dict, game_id: str) -> list[PlayerOdds]:
    results: list[PlayerOdds] = []
    for bookmaker in data.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market["key"] != "player_goal_scorer_anytime":
                continue
            for outcome in market.get("outcomes", []):
                price = int(outcome["price"])
                results.append(PlayerOdds(
                    player_name=outcome.get("description", outcome.get("name", "")),
                    game_id=game_id,
                    goal_line=0.5,
                    over_price=price,
                    implied_prob=round(_american_to_raw_prob(price), 4),
                    book=bookmaker.get("key", ""),
                ))
        break  # first bookmaker only
    return results


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _american_to_raw_prob(ml: int) -> float:
    if ml > 0:
        return 100.0 / (ml + 100.0)
    return abs(ml) / (abs(ml) + 100.0)


def _devig(raw_home: float, raw_away: float) -> tuple[float, float]:
    total = raw_home + raw_away
    if total <= 0:
        return 0.5, 0.5
    return raw_home / total, raw_away / total


def _api_key() -> str:
    key = os.getenv("ODDS_API_KEY")
    if not key:
        raise EnvironmentError("ODDS_API_KEY not set in environment")
    return key
