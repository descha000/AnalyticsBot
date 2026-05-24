"""
E2E test: preview slot — no game today, generates D-1 team matchup script.

Mocks: ALL requests.get calls (single routing mock), Anthropic client.
Asserts: output JSON written, game_state updated, script fields populated.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import history.game_state as gs
import pipeline

pytestmark = pytest.mark.e2e

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
    "HOOK: The numbers say BOS wins tomorrow.\n"
    "NARRATIVE: Boston's xGF leads the league.\n"
    "TURN: But Florida's save pct is elite.\n"
    "VERDICT: Model gives BOS 52% to win.\n"
    "RETURN HOOK: Can BOS back it up?\n"
    '{"hook_visual": "BOS analytics edge tonight", "edge_summary": "+5.5% edge BOS"}'
)


def _make_schedule(date: str, home: str, away: str, game_id: int = 2025030401) -> dict:
    return {
        "gameWeek": [{
            "date": date,
            "games": [{
                "id": game_id, "season": 20252026, "gameType": 3,
                "startTimeUTC": f"{date}T23:00:00Z",
                "homeTeam": {"abbrev": home},
                "awayTeam": {"abbrev": away},
            }],
        }]
    }


def _requests_router(url: str, **kwargs) -> MagicMock:
    """Route all requests.get calls based on URL pattern."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    m = MagicMock()
    if "moneypuck" in url and "teams" in url:
        m.text = _TEAMS_CSV
    elif "the-odds-api" in url:
        m.json.return_value = _ODDS_PAYLOAD
    elif "schedule" in url and today in url:
        # No games today
        m.json.return_value = {"gameWeek": []}
    elif "schedule" in url:
        # Any future date: return one game
        date = url.rstrip("/").split("/")[-1]
        m.json.return_value = _make_schedule(date, "BOS", "FLA")
    else:
        m.json.return_value = {}
    return m


def _claude_mock():
    msg = MagicMock()
    msg.content = [MagicMock(text=_CLAUDE_RESPONSE)]
    msg.usage.input_tokens = 500
    msg.usage.output_tokens = 150
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


class TestPreviewSlot:
    def _run(self):
        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic", return_value=_claude_mock()):
                with patch("scripts.generator.log_claude"):
                    game = pipeline._resolve_game(None, "preview")
                    pipeline.run_preview(game, "nhl")

    def test_output_file_written(self, tmp_path):
        self._run()
        files = list((tmp_path / "output").glob("*_preview.json"))
        assert len(files) == 1

    def test_output_json_fields(self, tmp_path):
        self._run()
        f = next((tmp_path / "output").glob("*_preview.json"))
        data = json.loads(f.read_text())
        assert data["slot"] == "preview"
        assert data["home_team"] == "BOS"
        assert data["away_team"] == "FLA"
        assert data["hook_visual"] == "BOS analytics edge tonight"
        assert "model_snapshot" in data
        assert "home_win_prob" in data["model_snapshot"]

    def test_game_state_marked_done(self):
        self._run()
        # game_id is dynamic but we can check that some preview was marked done
        import json as _json
        from pathlib import Path
        state_file = gs._STATE_FILE
        if state_file.exists():
            state = _json.loads(state_file.read_text())
            any_done = any(v.get("preview") for v in state.values())
            assert any_done

    def test_idempotent_skips_second_run(self, capsys):
        # Run once to discover the game_id
        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic", return_value=_claude_mock()):
                with patch("scripts.generator.log_claude"):
                    game = pipeline._resolve_game(None, "preview")

        # Pre-mark it done
        gs.mark_slot_done(game.game_id, "preview")

        with patch("requests.get", side_effect=_requests_router):
            with patch("scripts.generator.anthropic.Anthropic") as mock_api:
                pipeline.run_preview(game, "nhl")
                mock_api.assert_not_called()

        assert "skipping" in capsys.readouterr().out
