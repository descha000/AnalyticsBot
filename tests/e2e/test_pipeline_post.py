"""
E2E test: post slot — game is final, generates model-vs-reality script.

Mocks: ALL requests.get (single routing mock), Anthropic client.
Pre-seeds game_state with a model_snapshot from the pre slot.
Asserts: output references actual result, game_state updated.
"""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import history.game_state as gs
import pipeline

pytestmark = pytest.mark.e2e

_GAME_ID = "2025030401"

_BOXSCORE_FINAL = {
    "gameState": "OFF",
    "homeTeam": {"score": 3},
    "awayTeam": {"score": 2},
    "periodDescriptor": {"number": 3, "periodType": "REG"},
}

_TEAMS_CSV = (
    "team,season,situation,iceTime,xGoalsFor,xGoalsAgainst,goalsFor,goalsAgainst,"
    "shotsOnGoalFor,shotsOnGoalAgainst,gamesPlayed,powerPlayPct,penaltyKillPct\n"
    "BOS,2025,all,230400,242.0,204.0,250,210,2950,2700,82,0.225,0.838\n"
    "FLA,2025,all,228000,220.0,215.0,228,220,2720,2710,82,0.198,0.821\n"
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
    "HOOK: We called it — here's how the math played out.\n"
    "NARRATIVE: Our model gave Boston 52%. They delivered.\n"
    "TURN: The 5-goal total was slightly off — model said 5.4.\n"
    "VERDICT: Moneyline edge was correct; totals edge missed by 0.1.\n"
    "RETURN HOOK: Numbers don't lie — usually.\n"
    '{"hook_visual": "BOS model correct recap", "edge_summary": "Model hit moneyline, missed total"}'
)

_PRE_SNAPSHOT = {
    "home_win_prob": 0.52,
    "away_win_prob": 0.30,
    "expected_total": 5.45,
    "calibration_version": "uncalibrated_v0",
}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _requests_router(url: str, **kwargs) -> MagicMock:
    today = _today()
    m = MagicMock()
    m.status_code = 200
    if "moneypuck" in url and "teams" in url:
        m.text = _TEAMS_CSV
    elif "the-odds-api" in url:
        m.json.return_value = _ODDS_PAYLOAD
    elif "gamecenter" in url:
        m.json.return_value = _BOXSCORE_FINAL
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
    msg.usage.input_tokens = 650
    msg.usage.output_tokens = 170
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
    gs.save_model_snapshot(_GAME_ID, _PRE_SNAPSHOT)


class TestPostSlot:
    def _run(self):
        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic", return_value=_claude_mock()):
                with patch("scripts.generator.log_claude"):
                    game = pipeline._resolve_game(_GAME_ID, "post")
                    pipeline.run_post(game, "nhl")

    def test_output_file_written(self, tmp_path):
        self._run()
        files = list((tmp_path / "output").glob("*_post.json"))
        assert len(files) == 1

    def test_output_slot_is_post(self, tmp_path):
        self._run()
        f = next((tmp_path / "output").glob("*_post.json"))
        data = json.loads(f.read_text())
        assert data["slot"] == "post"

    def test_hook_visual_in_output(self, tmp_path):
        self._run()
        f = next((tmp_path / "output").glob("*_post.json"))
        data = json.loads(f.read_text())
        assert data["hook_visual"] == "BOS model correct recap"

    def test_game_state_marked_done(self):
        self._run()
        assert gs.is_slot_done(_GAME_ID, "post") is True

    def test_snapshot_used_in_prompt(self):
        """Verify the pre-event snapshot was passed to Claude (not re-derived)."""
        captured_prompts = []

        def capture_create(**kwargs):
            captured_prompts.append(kwargs.get("messages", [{}])[0].get("content", ""))
            msg = MagicMock()
            msg.content = [MagicMock(text=_CLAUDE_RESPONSE)]
            msg.usage.input_tokens = 650
            msg.usage.output_tokens = 170
            return msg

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = capture_create

        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic", return_value=mock_client):
                with patch("scripts.generator.log_claude"):
                    game = pipeline._resolve_game(_GAME_ID, "post")
                    pipeline.run_post(game, "nhl")

        assert len(captured_prompts) == 1
        # The snapshot's home_win_prob = 0.52 = 52.0% should appear in the prompt
        assert "52" in captured_prompts[0]

    def test_idempotent(self, capsys):
        gs.mark_slot_done(_GAME_ID, "post")
        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic") as mock_api:
                game = pipeline._resolve_game(_GAME_ID, "post")
                pipeline.run_post(game, "nhl")
                mock_api.assert_not_called()
        assert "skipping" in capsys.readouterr().out
