"""Unit tests for data/odds.py."""

import os
from unittest.mock import MagicMock, patch

import pytest

from data.odds import (
    GameOdds,
    PlayerOdds,
    _american_to_raw_prob,
    _devig,
    _parse_game_odds,
    _parse_player_odds,
    fetch_game_odds,
    fetch_player_odds,
    match_odds_to_games,
)

# ---------------------------------------------------------------------------
# Sample API payloads
# ---------------------------------------------------------------------------

_ODDS_PAYLOAD = [
    {
        "id": "event_abc",
        "sport_key": "icehockey_nhl",
        "home_team": "Boston Bruins",
        "away_team": "Florida Panthers",
        "bookmakers": [
            {
                "key": "draftkings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": "Boston Bruins", "price": -145},
                            {"name": "Florida Panthers", "price": 122},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 5.5, "price": -110},
                            {"name": "Under", "point": 5.5, "price": -110},
                        ],
                    },
                ],
            }
        ],
    }
]

_PLAYER_PROPS_PAYLOAD = {
    "bookmakers": [
        {
            "key": "draftkings",
            "markets": [
                {
                    "key": "player_goal_scorer_anytime",
                    "outcomes": [
                        {"description": "David Pastrnak", "name": "Yes", "price": 220},
                        {"description": "Matthew Tkachuk", "name": "Yes", "price": 260},
                    ],
                }
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

class TestAmericanToRawProb:
    def test_negative_favourite(self):
        # -145 → 145/245 ≈ 0.5918
        assert _american_to_raw_prob(-145) == pytest.approx(145 / 245, rel=1e-4)

    def test_positive_underdog(self):
        # +122 → 100/222 ≈ 0.4505
        assert _american_to_raw_prob(122) == pytest.approx(100 / 222, rel=1e-4)

    def test_even_money(self):
        assert _american_to_raw_prob(100) == pytest.approx(0.5, rel=1e-4)

    def test_minus_100(self):
        assert _american_to_raw_prob(-100) == pytest.approx(0.5, rel=1e-4)


class TestDevig:
    def test_sums_to_one(self):
        h, a = _devig(0.55, 0.50)
        assert h + a == pytest.approx(1.0, rel=1e-6)

    def test_higher_raw_prob_stays_higher(self):
        h, a = _devig(0.55, 0.50)
        assert h > a

    def test_zero_total_returns_even(self):
        h, a = _devig(0.0, 0.0)
        assert h == pytest.approx(0.5)
        assert a == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

class TestParseGameOdds:
    def test_returns_list(self):
        results = _parse_game_odds(_ODDS_PAYLOAD)
        assert isinstance(results, list)
        assert len(results) == 1

    def test_team_abbrevs_mapped_correctly(self):
        result = _parse_game_odds(_ODDS_PAYLOAD)[0]
        assert result.home_team == "BOS"
        assert result.away_team == "FLA"

    def test_moneylines_parsed(self):
        result = _parse_game_odds(_ODDS_PAYLOAD)[0]
        assert result.home_moneyline == -145
        assert result.away_moneyline == 122

    def test_implied_probs_sum_to_one(self):
        result = _parse_game_odds(_ODDS_PAYLOAD)[0]
        assert result.home_implied_prob + result.away_implied_prob == pytest.approx(1.0, abs=1e-3)

    def test_total_line_parsed(self):
        result = _parse_game_odds(_ODDS_PAYLOAD)[0]
        assert result.total_line == 5.5

    def test_odds_event_id(self):
        result = _parse_game_odds(_ODDS_PAYLOAD)[0]
        assert result.odds_event_id == "event_abc"

    def test_game_id_empty_initially(self):
        result = _parse_game_odds(_ODDS_PAYLOAD)[0]
        assert result.game_id == ""

    def test_skips_events_with_no_moneyline(self):
        no_ml = [{"id": "x", "home_team": "BOS", "away_team": "FLA", "bookmakers": []}]
        results = _parse_game_odds(no_ml)
        assert results == []


class TestParsePlayerOdds:
    def test_returns_player_odds(self):
        results = _parse_player_odds(_PLAYER_PROPS_PAYLOAD, "2025030401")
        assert len(results) == 2

    def test_player_name_from_description(self):
        results = _parse_player_odds(_PLAYER_PROPS_PAYLOAD, "2025030401")
        names = [r.player_name for r in results]
        assert "David Pastrnak" in names

    def test_game_id_set(self):
        results = _parse_player_odds(_PLAYER_PROPS_PAYLOAD, "2025030401")
        assert all(r.game_id == "2025030401" for r in results)

    def test_implied_prob_positive(self):
        results = _parse_player_odds(_PLAYER_PROPS_PAYLOAD, "2025030401")
        assert all(r.implied_prob > 0 for r in results)


# ---------------------------------------------------------------------------
# match_odds_to_games
# ---------------------------------------------------------------------------

class TestMatchOddsToGames:
    def test_matches_by_team_abbrev(self, boston_game, boston_odds):
        boston_odds.game_id = ""
        matched = match_odds_to_games([boston_game], [boston_odds])
        assert "2025030401" in matched

    def test_sets_game_id_on_odds(self, boston_game, boston_odds):
        boston_odds.game_id = ""
        match_odds_to_games([boston_game], [boston_odds])
        assert boston_odds.game_id == "2025030401"

    def test_returns_empty_when_no_match(self, boston_game):
        from data.odds import GameOdds
        wrong_odds = GameOdds(
            game_id="", odds_event_id="x", home_team="NYR", away_team="MTL",
            home_moneyline=-110, away_moneyline=-110,
            home_implied_prob=0.5, away_implied_prob=0.5,
            total_line=5.5, book="dk",
        )
        matched = match_odds_to_games([boston_game], [wrong_odds])
        assert matched == {}


# ---------------------------------------------------------------------------
# API functions (mocked)
# ---------------------------------------------------------------------------

class TestFetchGameOdds:
    def test_calls_api_with_key(self, monkeypatch):
        monkeypatch.setenv("ODDS_API_KEY", "test_key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = _ODDS_PAYLOAD
        with patch("data.odds.requests.get", return_value=mock_resp) as mock_get:
            fetch_game_odds()
            params = mock_get.call_args[1]["params"]
            assert params["apiKey"] == "test_key"

    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ODDS_API_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="ODDS_API_KEY"):
            fetch_game_odds()
