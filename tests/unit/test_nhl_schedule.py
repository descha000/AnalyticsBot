"""Unit tests for data/nhl_schedule.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from data.nhl_schedule import (
    GameResult,
    NHLGame,
    _current_season,
    _parse_result,
    _parse_schedule,
    fetch_game_result,
    fetch_games_on_date,
    fetch_next_game,
    fetch_today_games,
)

# ---------------------------------------------------------------------------
# Sample API payloads
# ---------------------------------------------------------------------------

_SCHEDULE_PAYLOAD = {
    "gameWeek": [
        {
            "date": "2026-05-23",
            "games": [
                {
                    "id": 2025030401,
                    "season": 20252026,
                    "gameType": 3,
                    "startTimeUTC": "2026-05-23T23:00:00Z",
                    "homeTeam": {"abbrev": "BOS"},
                    "awayTeam": {"abbrev": "FLA"},
                }
            ],
        }
    ]
}

_BOXSCORE_FINAL = {
    "gameState": "OFF",
    "homeTeam": {"score": 3},
    "awayTeam": {"score": 2},
    "periodDescriptor": {"number": 3, "periodType": "REG"},
}

_BOXSCORE_OT = {
    "gameState": "OFF",
    "homeTeam": {"score": 2},
    "awayTeam": {"score": 3},
    "periodDescriptor": {"number": 4, "periodType": "OT"},
}

_BOXSCORE_NOT_FINAL = {
    "gameState": "LIVE",
    "homeTeam": {"score": 1},
    "awayTeam": {"score": 1},
    "periodDescriptor": {"number": 2, "periodType": "REG"},
}


# ---------------------------------------------------------------------------
# _parse_schedule
# ---------------------------------------------------------------------------

class TestParseSchedule:
    def test_parses_correct_date(self):
        games = _parse_schedule(_SCHEDULE_PAYLOAD, "2026-05-23")
        assert len(games) == 1

    def test_ignores_other_dates(self):
        games = _parse_schedule(_SCHEDULE_PAYLOAD, "2026-05-24")
        assert len(games) == 0

    def test_game_fields(self):
        game = _parse_schedule(_SCHEDULE_PAYLOAD, "2026-05-23")[0]
        assert game.game_id == "2025030401"
        assert game.home_team == "BOS"
        assert game.away_team == "FLA"
        assert game.game_type == "playoff"
        assert game.season == "20252026"

    def test_start_time_is_utc(self):
        game = _parse_schedule(_SCHEDULE_PAYLOAD, "2026-05-23")[0]
        assert game.start_time_utc.tzinfo is not None
        assert game.start_time_utc == datetime(2026, 5, 23, 23, 0, tzinfo=timezone.utc)

    def test_estimated_end_after_start(self):
        game = _parse_schedule(_SCHEDULE_PAYLOAD, "2026-05-23")[0]
        assert game.estimated_end_utc > game.start_time_utc

    def test_regular_season_game_type(self):
        payload = {
            "gameWeek": [{
                "date": "2026-01-15",
                "games": [{
                    "id": 2025020001, "season": 20252026, "gameType": 2,
                    "startTimeUTC": "2026-01-15T00:00:00Z",
                    "homeTeam": {"abbrev": "NYR"}, "awayTeam": {"abbrev": "NJD"},
                }],
            }]
        }
        game = _parse_schedule(payload, "2026-01-15")[0]
        assert game.game_type == "regular"


# ---------------------------------------------------------------------------
# _parse_result
# ---------------------------------------------------------------------------

class TestParseResult:
    def test_final_reg(self):
        result = _parse_result(_BOXSCORE_FINAL, "2025030401")
        assert result.home_score == 3
        assert result.away_score == 2
        assert result.went_to_ot is False
        assert result.final_period == "REG"

    def test_final_ot(self):
        result = _parse_result(_BOXSCORE_OT, "2025030401")
        assert result.went_to_ot is True
        assert result.final_period == "OT"

    def test_not_final_returns_none(self):
        result = _parse_result(_BOXSCORE_NOT_FINAL, "2025030401")
        assert result is None

    def test_game_id_preserved(self):
        result = _parse_result(_BOXSCORE_FINAL, "2025030401")
        assert result.game_id == "2025030401"


# ---------------------------------------------------------------------------
# Network-dependent functions (mocked)
# ---------------------------------------------------------------------------

class TestFetchGamesOnDate:
    def test_calls_correct_url(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _SCHEDULE_PAYLOAD
        with patch("data.nhl_schedule.requests.get", return_value=mock_resp) as mock_get:
            fetch_games_on_date("2026-05-23")
            mock_get.assert_called_once()
            assert "2026-05-23" in mock_get.call_args[0][0]

    def test_returns_list_of_nhl_games(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _SCHEDULE_PAYLOAD
        with patch("data.nhl_schedule.requests.get", return_value=mock_resp):
            games = fetch_games_on_date("2026-05-23")
        assert isinstance(games, list)
        assert all(isinstance(g, NHLGame) for g in games)


class TestFetchGameResult:
    def test_returns_none_on_404(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("data.nhl_schedule.requests.get", return_value=mock_resp):
            result = fetch_game_result("2025030401")
        assert result is None

    def test_returns_none_when_not_final(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _BOXSCORE_NOT_FINAL
        with patch("data.nhl_schedule.requests.get", return_value=mock_resp):
            result = fetch_game_result("2025030401")
        assert result is None

    def test_returns_result_when_final(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _BOXSCORE_FINAL
        with patch("data.nhl_schedule.requests.get", return_value=mock_resp):
            result = fetch_game_result("2025030401")
        assert isinstance(result, GameResult)


class TestFetchNextGame:
    def test_returns_first_future_game(self):
        call_count = [0]

        def mock_get(url, **kwargs):
            m = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                # day+1: no games
                m.json.return_value = {"gameWeek": []}
            else:
                # day+2+: return games for whatever date was requested
                date = url.rstrip("/").split("/")[-1]
                m.json.return_value = {
                    "gameWeek": [{
                        "date": date,
                        "games": [{
                            "id": 2025030402, "season": 20252026, "gameType": 3,
                            "startTimeUTC": f"{date}T23:00:00Z",
                            "homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "VGK"},
                        }],
                    }]
                }
            return m

        with patch("data.nhl_schedule.requests.get", side_effect=mock_get):
            game = fetch_next_game()
        assert game is not None

    def test_returns_none_when_no_games_in_7_days(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"gameWeek": []}
        with patch("data.nhl_schedule.requests.get", return_value=mock_resp):
            game = fetch_next_game()
        assert game is None


_SCHEDULE_PAYLOAD_TOMORROW = {
    "gameWeek": [{
        "date": "2026-05-25",
        "games": [{
            "id": 2025030402, "season": 20252026, "gameType": 3,
            "startTimeUTC": "2026-05-25T23:00:00Z",
            "homeTeam": {"abbrev": "EDM"}, "awayTeam": {"abbrev": "VGK"},
        }],
    }]
}


# ---------------------------------------------------------------------------
# _current_season
# ---------------------------------------------------------------------------

class TestCurrentSeason:
    def test_format(self):
        season = _current_season()
        assert len(season) == 8
        assert season.isdigit()
