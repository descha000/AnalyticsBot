"""
E2E test: pre slot — game today, generates player props script 6h before.

Mocks: ALL requests.get (single routing mock), Anthropic client.
Asserts: output JSON written with player picks, game_state updated.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import history.game_state as gs
import pipeline

pytestmark = pytest.mark.e2e

_GAME_ID = "2025030401"

_TEAMS_CSV = (
    "team,season,situation,iceTime,xGoalsFor,xGoalsAgainst,goalsFor,goalsAgainst,"
    "shotsOnGoalFor,shotsOnGoalAgainst,gamesPlayed,powerPlayPct,penaltyKillPct\n"
    "BOS,2025,all,230400,242.0,204.0,250,210,2950,2700,82,0.225,0.838\n"
    "FLA,2025,all,228000,220.0,215.0,228,220,2720,2710,82,0.198,0.821\n"
)

_SKATERS_CSV = (
    "playerId,name,team,position,season,situation,games_played,icetime,I_F_goals,I_F_shotsOnGoal\n"
    "8478402,David Pastrnak,BOS,R,2025,all,72,84240,40,258\n"
    "8479318,Brad Marchand,BOS,L,2025,all,68,79560,30,210\n"
    "8481528,Sam Reinhart,FLA,C,2025,all,80,92000,45,290\n"
)

_ODDS_PAYLOAD = [{
    "id": "event_abc",
    "sport_key": "icehockey_nhl",
    "home_team": "Boston Bruins",
    "away_team": "Florida Panthers",
    "bookmakers": [{
        "key": "draftkings",
        "markets": [
            {"key": "h2h", "outcomes": [
                {"name": "Boston Bruins", "price": -145},
                {"name": "Florida Panthers", "price": 122},
            ]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": 5.5, "price": -110},
                {"name": "Under", "point": 5.5, "price": -110},
            ]},
        ],
    }],
}]

_CLAUDE_RESPONSE = (
    "HOOK: Tonight's goals race is on.\n"
    "NARRATIVE: Pastrnak leads Boston's attack with elite shot volume.\n"
    "TURN: But Reinhart has been unstoppable in Florida.\n"
    "VERDICT: Model likes Pastrnak to score — 20% goal probability.\n"
    "RETURN HOOK: Will the numbers deliver tonight?\n"
    '{"hook_visual": "Pastrnak scores tonight analytics", "edge_summary": "Pastrnak 20% goal prob"}'
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _requests_router(url: str, **kwargs) -> MagicMock:
    today = _today()
    m = MagicMock()
    if "moneypuck" in url and "teams" in url:
        m.text = _TEAMS_CSV
    elif "moneypuck" in url and "skaters" in url:
        m.text = _SKATERS_CSV
    elif "the-odds-api" in url:
        m.json.return_value = _ODDS_PAYLOAD
    elif "schedule" in url:
        m.json.return_value = {
            "gameWeek": [{
                "date": today,
                "games": [{
                    "id": int(_GAME_ID), "season": 20252026, "gameType": 3,
                    "startTimeUTC": f"{today}T23:00:00Z",
                    "homeTeam": {"abbrev": "BOS"},
                    "awayTeam": {"abbrev": "FLA"},
                }],
            }]
        }
    else:
        m.json.return_value = {}
    return m


def _claude_mock():
    msg = MagicMock()
    msg.content = [MagicMock(text=_CLAUDE_RESPONSE)]
    msg.usage.input_tokens = 600
    msg.usage.output_tokens = 160
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    monkeypatch.setenv("ODDS_API_KEY", "test_odds_key")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gs, "_STATE_FILE", tmp_path / "game_state.json")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path / "output")


class TestPreSlot:
    def _run(self):
        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic", return_value=_claude_mock()):
                with patch("scripts.generator.log_claude"):
                    game = pipeline._resolve_game(_GAME_ID, "pre")
                    pipeline.run_pre(game, "nhl")

    def test_output_file_written(self, tmp_path):
        self._run()
        files = list((tmp_path / "output").glob("*_pre.json"))
        assert len(files) == 1

    def test_output_json_slot_is_pre(self, tmp_path):
        self._run()
        f = next((tmp_path / "output").glob("*_pre.json"))
        data = json.loads(f.read_text())
        assert data["slot"] == "pre"

    def test_hook_visual_in_output(self, tmp_path):
        self._run()
        f = next((tmp_path / "output").glob("*_pre.json"))
        data = json.loads(f.read_text())
        assert data["hook_visual"] == "Pastrnak scores tonight analytics"

    def test_game_state_marked_done(self):
        self._run()
        assert gs.is_slot_done(_GAME_ID, "pre") is True

    def test_model_snapshot_saved(self):
        self._run()
        snapshot = gs.get_model_snapshot(_GAME_ID)
        assert snapshot is not None
        assert "home_win_prob" in snapshot

    def test_idempotent(self, capsys):
        gs.mark_slot_done(_GAME_ID, "pre")
        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic") as mock_api:
                game = pipeline._resolve_game(_GAME_ID, "pre")
                pipeline.run_pre(game, "nhl")
                mock_api.assert_not_called()
        assert "skipping" in capsys.readouterr().out
