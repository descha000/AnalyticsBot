"""Unit tests for data/nhl_client.py — all nhlpy calls mocked."""

from unittest.mock import MagicMock, patch

import pytest

from data.nhl_client import (
    GoalieSavePct,
    PlayerRecentForm,
    fetch_game_scratches,
    fetch_goalie_save_pct,
    fetch_player_recent_form,
    fetch_team_goalie_ids,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_client():
    """Reset the cached NHLClient singleton between tests."""
    import data.nhl_client as mod
    original = mod._client
    mod._client = None
    yield
    mod._client = original


@pytest.fixture
def mock_nhl():
    with patch("data.nhl_client.NHLClient") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


# ---------------------------------------------------------------------------
# fetch_game_scratches
# ---------------------------------------------------------------------------

class TestFetchGameScratches:
    def test_returns_player_ids(self, mock_nhl):
        mock_nhl.game_center.season_series_matchup.return_value = {
            "gameInfo": {
                "scratches": [
                    {"playerId": "8478402"},
                    {"playerId": "8476945"},
                ]
            }
        }
        result = fetch_game_scratches("2025030313")
        assert result == {"8478402", "8476945"}

    def test_returns_empty_on_no_scratches_key(self, mock_nhl):
        mock_nhl.game_center.season_series_matchup.return_value = {"gameInfo": {}}
        result = fetch_game_scratches("2025030313")
        assert result == set()

    def test_returns_empty_on_api_error(self, mock_nhl):
        mock_nhl.game_center.season_series_matchup.side_effect = Exception("network error")
        result = fetch_game_scratches("2025030313")
        assert result == set()

    def test_handles_id_fallback(self, mock_nhl):
        mock_nhl.game_center.season_series_matchup.return_value = {
            "gameInfo": {"scratches": [{"id": "9999999"}]}
        }
        result = fetch_game_scratches("2025030313")
        assert "9999999" in result


# ---------------------------------------------------------------------------
# fetch_goalie_save_pct
# ---------------------------------------------------------------------------

class TestFetchGoalieSavePct:
    def test_returns_save_pct(self, mock_nhl):
        mock_nhl.edge.goalie_save_percentage_detail.return_value = {
            "overallSavePctg": 0.923,
            "highDangerSavePctg": 0.855,
        }
        result = fetch_goalie_save_pct("8476945")
        assert isinstance(result, GoalieSavePct)
        assert result.overall_sv_pct == pytest.approx(0.923)
        assert result.high_danger_sv_pct == pytest.approx(0.855)

    def test_returns_none_when_no_overall(self, mock_nhl):
        mock_nhl.edge.goalie_save_percentage_detail.return_value = {}
        result = fetch_goalie_save_pct("8476945")
        assert result is None

    def test_returns_none_on_api_error(self, mock_nhl):
        mock_nhl.edge.goalie_save_percentage_detail.side_effect = Exception("timeout")
        result = fetch_goalie_save_pct("8476945")
        assert result is None

    def test_high_danger_none_when_missing(self, mock_nhl):
        mock_nhl.edge.goalie_save_percentage_detail.return_value = {
            "overallSavePctg": 0.910,
        }
        result = fetch_goalie_save_pct("8476945")
        assert result is not None
        assert result.high_danger_sv_pct is None


# ---------------------------------------------------------------------------
# fetch_player_recent_form
# ---------------------------------------------------------------------------

class TestFetchPlayerRecentForm:
    _sample_log = [
        {"goals": 1, "assists": 0, "shots": 4},
        {"goals": 0, "assists": 2, "shots": 3},
        {"goals": 1, "assists": 1, "shots": 5},
        {"goals": 0, "assists": 0, "shots": 2},
        {"goals": 1, "assists": 0, "shots": 6},
        {"goals": 2, "assists": 1, "shots": 8},  # 6th game — outside last_n=5 window
    ]

    def test_aggregates_last_n_games(self, mock_nhl):
        mock_nhl.stats.player_game_log.return_value = self._sample_log
        result = fetch_player_recent_form("8478402", last_n=5)
        assert isinstance(result, PlayerRecentForm)
        assert result.games_played == 5
        assert result.goals == 3   # 1+0+1+0+1
        assert result.assists == 3  # 0+2+1+0+0
        assert result.shots == 20  # 4+3+5+2+6

    def test_goals_per_game_computed(self, mock_nhl):
        mock_nhl.stats.player_game_log.return_value = self._sample_log
        result = fetch_player_recent_form("8478402", last_n=5)
        assert result.goals_per_game == pytest.approx(0.6, rel=0.01)

    def test_returns_none_on_empty_log(self, mock_nhl):
        mock_nhl.stats.player_game_log.return_value = []
        result = fetch_player_recent_form("8478402")
        assert result is None

    def test_returns_none_on_api_error(self, mock_nhl):
        mock_nhl.stats.player_game_log.side_effect = Exception("404")
        result = fetch_player_recent_form("8478402")
        assert result is None

    def test_partial_log_when_fewer_than_n_games(self, mock_nhl):
        mock_nhl.stats.player_game_log.return_value = self._sample_log[:2]
        result = fetch_player_recent_form("8478402", last_n=5)
        assert result.games_played == 2


# ---------------------------------------------------------------------------
# fetch_team_goalie_ids
# ---------------------------------------------------------------------------

class TestFetchTeamGoalieIds:
    def test_returns_goalie_ids(self, mock_nhl):
        mock_nhl.teams.team_roster.return_value = {
            "goalies": [{"id": "8476945"}, {"id": "8479973"}]
        }
        result = fetch_team_goalie_ids("BOS")
        assert result == ["8476945", "8479973"]

    def test_returns_empty_on_no_goalies(self, mock_nhl):
        mock_nhl.teams.team_roster.return_value = {"goalies": []}
        result = fetch_team_goalie_ids("BOS")
        assert result == []

    def test_returns_empty_on_api_error(self, mock_nhl):
        mock_nhl.teams.team_roster.side_effect = Exception("error")
        result = fetch_team_goalie_ids("BOS")
        assert result == []
