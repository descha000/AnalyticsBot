"""Unit tests for scripts/generator.py."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.generator import (
    AnalyticsPayload,
    AnalyticsScript,
    _build_prompt,
    _parse_response,
    generate_script,
)


@pytest.fixture
def preview_payload(boston_game, sample_poisson, sample_edge):
    return AnalyticsPayload(
        game=boston_game,
        slot="preview",
        edge=sample_edge,
        poisson=sample_poisson,
        player_picks=[],
        actual_result=None,
        model_snapshot=None,
    )


@pytest.fixture
def pre_payload(boston_game, sample_poisson, sample_edge):
    from models.player_model import PlayerPoissonResult
    picks = [
        PlayerPoissonResult("David Pastrnak", "BOS", 0.22, 0.20, 0.04, "uncalibrated_v0"),
        PlayerPoissonResult("Matthew Tkachuk", "FLA", 0.19, 0.18, 0.03, "uncalibrated_v0"),
    ]
    return AnalyticsPayload(
        game=boston_game,
        slot="pre",
        edge=sample_edge,
        poisson=sample_poisson,
        player_picks=picks,
        actual_result=None,
        model_snapshot=None,
    )


@pytest.fixture
def post_payload(boston_game, sample_poisson, sample_edge, final_result):
    return AnalyticsPayload(
        game=boston_game,
        slot="post",
        edge=sample_edge,
        poisson=sample_poisson,
        player_picks=[],
        actual_result=final_result,
        model_snapshot={"home_win_prob": 0.52, "expected_total": 5.45},
    )


class TestBuildPrompt:
    def test_preview_contains_team_names(self, preview_payload):
        prompt = _build_prompt(preview_payload)
        assert "BOS" in prompt
        assert "FLA" in prompt

    def test_preview_contains_win_prob(self, preview_payload):
        prompt = _build_prompt(preview_payload)
        assert "%" in prompt

    def test_pre_contains_player_picks(self, pre_payload):
        prompt = _build_prompt(pre_payload)
        assert "David Pastrnak" in prompt
        assert "Matthew Tkachuk" in prompt

    def test_post_contains_final_score(self, post_payload):
        prompt = _build_prompt(post_payload)
        assert "3" in prompt  # home score
        assert "2" in prompt  # away score

    def test_post_contains_model_snapshot(self, post_payload):
        prompt = _build_prompt(post_payload)
        assert "52" in prompt  # 0.52 home win prob

    def test_different_slots_produce_different_prompts(
        self, preview_payload, pre_payload, post_payload
    ):
        prompts = {
            _build_prompt(preview_payload),
            _build_prompt(pre_payload),
            _build_prompt(post_payload),
        }
        assert len(prompts) == 3


class TestParseResponse:
    def test_extracts_json_block(self, preview_payload):
        raw = (
            "HOOK: This is the hook.\nNARRATIVE: some text.\n"
            '{"hook_visual": "BOS vs FLA tonight", "edge_summary": "+5% edge on BOS"}'
        )
        body, hook, edge = _parse_response(raw, preview_payload)
        assert hook == "BOS vs FLA tonight"
        assert edge == "+5% edge on BOS"
        assert "HOOK" in body

    def test_fallback_on_no_json(self, preview_payload):
        raw = "HOOK: Just a script with no JSON at the end."
        body, hook, edge = _parse_response(raw, preview_payload)
        assert body == raw
        assert isinstance(hook, str)
        assert isinstance(edge, str)
        assert len(hook) > 0
        assert len(edge) > 0

    def test_fallback_on_malformed_json(self, preview_payload):
        raw = 'Some script. {"hook_visual": "incomplete'
        body, hook, edge = _parse_response(raw, preview_payload)
        assert isinstance(hook, str)


class TestGenerateScript:
    def _make_mock_message(self, text: str):
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=text)]
        mock_msg.usage.input_tokens = 500
        mock_msg.usage.output_tokens = 150
        return mock_msg

    def test_returns_analytics_script(self, preview_payload, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
        mock_resp_text = (
            "HOOK: The numbers say BOS wins tonight.\n"
            "NARRATIVE: Boston's xGF leads the league.\n"
            "TURN: But Florida's save pct is elite.\n"
            "VERDICT: Model gives BOS 52% to win.\n"
            "RETURN HOOK: Can BOS back it up?\n"
            '{"hook_visual": "BOS dominates analytics", "edge_summary": "+5% edge BOS"}'
        )
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._make_mock_message(mock_resp_text)

        with patch("scripts.generator.anthropic.Anthropic", return_value=mock_client):
            with patch("scripts.generator.log_claude"):
                result = generate_script(preview_payload)

        assert isinstance(result, AnalyticsScript)
        assert result.game_id == "2025030401"
        assert result.slot == "preview"
        assert result.hook_visual == "BOS dominates analytics"
        assert result.edge_summary == "+5% edge BOS"

    def test_model_snapshot_in_output(self, preview_payload, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = self._make_mock_message(
            'Script text. {"hook_visual": "x", "edge_summary": "y"}'
        )
        with patch("scripts.generator.anthropic.Anthropic", return_value=mock_client):
            with patch("scripts.generator.log_claude"):
                result = generate_script(preview_payload)

        assert "home_win_prob" in result.model_snapshot
        assert "expected_total" in result.model_snapshot

    def test_raises_without_api_key(self, preview_payload, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            generate_script(preview_payload)
