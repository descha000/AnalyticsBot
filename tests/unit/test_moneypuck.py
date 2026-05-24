"""Unit tests for data/moneypuck.py."""

from unittest.mock import MagicMock, patch

import pytest

from data.moneypuck import (
    PlayerStats,
    TeamStats,
    _parse_skaters,
    _parse_teams,
    _safe_float,
    fetch_player_stats,
    fetch_team_stats,
)

# ---------------------------------------------------------------------------
# Sample CSV data
# ---------------------------------------------------------------------------

_TEAMS_CSV = """\
team,season,situation,iceTime,xGoalsFor,xGoalsAgainst,goalsFor,goalsAgainst,shotsOnGoalFor,shotsOnGoalAgainst,gamesPlayed,powerPlayPct,penaltyKillPct
BOS,2025,all,230400,242.0,204.0,250,210,2950,2700,82,0.225,0.838
BOS,2025,5on5,180000,190.0,165.0,200,170,2400,2200,82,,
FLA,2025,all,228000,220.0,215.0,228,220,2720,2710,82,0.198,0.821
"""

_SKATERS_CSV = """\
playerId,name,team,position,season,situation,games_played,icetime,I_F_goals,I_F_shotsOnGoal
8478402,David Pastrnak,BOS,R,2025,all,72,84240,40,258
8479318,Brad Marchand,BOS,L,2025,all,68,79560,30,210
8478402,David Pastrnak,BOS,R,2025,5on5,72,65000,30,200
8480801,Matthew Tkachuk,FLA,L,2025,all,80,92000,45,290
"""


class TestParseTeams:
    def test_returns_dict_keyed_by_team(self):
        result = _parse_teams(_TEAMS_CSV)
        assert "BOS" in result
        assert "FLA" in result

    def test_filters_to_all_situation_only(self):
        result = _parse_teams(_TEAMS_CSV)
        # 5on5 row for BOS should not create a second entry
        assert len(result) == 2

    def test_games_played(self):
        result = _parse_teams(_TEAMS_CSV)
        assert result["BOS"].games_played == 82

    def test_xgf_per_game(self):
        result = _parse_teams(_TEAMS_CSV)
        assert result["BOS"].xgf_per_game == pytest.approx(242.0 / 82, rel=1e-4)

    def test_xga_per_game(self):
        result = _parse_teams(_TEAMS_CSV)
        assert result["BOS"].xga_per_game == pytest.approx(204.0 / 82, rel=1e-4)

    def test_save_pct_calculation(self):
        # BOS: goals_against=210, shots_against=2700 → save_pct = 1 - 210/2700
        result = _parse_teams(_TEAMS_CSV)
        expected = 1.0 - 210 / 2700
        assert result["BOS"].save_pct == pytest.approx(expected, rel=1e-4)

    def test_pp_pct_parsed(self):
        result = _parse_teams(_TEAMS_CSV)
        assert result["BOS"].pp_pct == pytest.approx(0.225, rel=1e-4)

    def test_shot_rate_60_positive(self):
        result = _parse_teams(_TEAMS_CSV)
        assert result["BOS"].shot_rate_60 > 0

    def test_returns_team_stats_instances(self):
        result = _parse_teams(_TEAMS_CSV)
        assert isinstance(result["BOS"], TeamStats)


class TestParseSkaters:
    def test_filters_all_situation_only(self):
        players = _parse_skaters(_SKATERS_CSV, team_filter=None)
        # Only 2 all-situation rows for BOS + FLA
        assert len(players) == 3

    def test_team_filter_works(self):
        players = _parse_skaters(_SKATERS_CSV, team_filter="BOS")
        assert all(p.team == "BOS" for p in players)
        assert len(players) == 2

    def test_shots_per_60_calculation(self):
        players = _parse_skaters(_SKATERS_CSV, team_filter="BOS")
        pastrnak = next(p for p in players if p.player_name == "David Pastrnak")
        # ice_hours = 84240 / 3600 = 23.4; shots_per_60 = 258 / 23.4
        expected = 258 / (84240 / 3600)
        assert pastrnak.shots_per_60 == pytest.approx(expected, rel=1e-3)

    def test_shooting_pct_calculation(self):
        players = _parse_skaters(_SKATERS_CSV, team_filter="BOS")
        pastrnak = next(p for p in players if p.player_name == "David Pastrnak")
        expected = 40 / 258
        assert pastrnak.shooting_pct == pytest.approx(expected, rel=1e-3)

    def test_toi_per_game(self):
        players = _parse_skaters(_SKATERS_CSV, team_filter="BOS")
        pastrnak = next(p for p in players if p.player_name == "David Pastrnak")
        # 84240 seconds / 72 games / 60 = minutes per game
        expected = 84240 / 72 / 60
        assert pastrnak.toi_per_game == pytest.approx(expected, rel=1e-3)

    def test_returns_player_stats_instances(self):
        players = _parse_skaters(_SKATERS_CSV, team_filter=None)
        assert all(isinstance(p, PlayerStats) for p in players)


class TestSafeFloat:
    def test_valid_string(self):
        assert _safe_float("0.225") == pytest.approx(0.225)

    def test_none_returns_zero(self):
        assert _safe_float(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert _safe_float("") == 0.0

    def test_invalid_string_returns_zero(self):
        assert _safe_float("n/a") == 0.0


class TestFetchFunctions:
    def test_fetch_team_stats_calls_url(self):
        mock_resp = MagicMock()
        mock_resp.text = _TEAMS_CSV
        with patch("data.moneypuck.requests.get", return_value=mock_resp) as mock_get:
            result = fetch_team_stats("2025")
            mock_get.assert_called_once()
            assert "2025" in mock_get.call_args[0][0]
        assert isinstance(result, dict)

    def test_fetch_player_stats_calls_url(self):
        mock_resp = MagicMock()
        mock_resp.text = _SKATERS_CSV
        with patch("data.moneypuck.requests.get", return_value=mock_resp) as mock_get:
            result = fetch_player_stats("2025", team="BOS")
            mock_get.assert_called_once()
        assert isinstance(result, list)
