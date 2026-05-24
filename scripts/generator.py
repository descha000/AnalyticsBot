"""
Claude script generator for AnalyticsBot.

Produces a 40-45 second YouTube Shorts script in the 5-beat format:
  hook / narrative / turn / verdict / return hook

Model: claude-sonnet-4-20250514
Output: AnalyticsScript dataclass written to output/{game_id}_{slot}.json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv

from costs.tracker import log_claude
from data.nhl_schedule import GameResult, NHLGame
from data.odds import GameOdds
from models.edge import BettingEdge
from models.player_model import PlayerPoissonResult
from models.team_model import PoissonResult

load_dotenv()

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 600

_SYSTEM_PROMPT = """\
You write 40-45 second YouTube Shorts scripts for a sports analytics channel.

Use the 5-beat format exactly — label each beat:
HOOK: grab attention in 1-2 sentences referencing the matchup and the key edge
NARRATIVE: 2-3 sentences of context using the advanced stats provided
TURN: 1-2 sentences introducing the surprising or counter-intuitive finding
VERDICT: 1-2 sentences stating the model's pick and confidence level
RETURN HOOK: 1 sentence callback to the opening hook

Rules:
- 120-140 words total (maps to 40-45 seconds at average speaking pace)
- No emojis, no hashtags, no "Like and subscribe"
- Plain conversational language — define any jargon briefly
- Numbers must be concrete: percentages, expected goals, moneyline values
- After the script, output a JSON block like this (no markdown code fences needed):
  {"hook_visual": "5-6 word thumbnail caption", "edge_summary": "one-phrase edge description"}
"""


@dataclass
class AnalyticsPayload:
    game: NHLGame
    slot: str                                       # "preview" | "pre" | "post"
    edge: BettingEdge
    poisson: PoissonResult
    player_picks: list[PlayerPoissonResult]         # pre slot only
    actual_result: GameResult | None                # post slot only
    model_snapshot: dict | None                     # post slot: pre-event prediction


@dataclass
class AnalyticsScript:
    game_id: str
    slot: str
    home_team: str
    away_team: str
    game_time_utc: str
    script_body: str
    hook_visual: str
    edge_summary: str
    model_snapshot: dict
    created_at: str


def generate_script(payload: AnalyticsPayload) -> AnalyticsScript:
    client = anthropic.Anthropic(api_key=_anthropic_key())
    prompt = _build_prompt(payload)

    msg = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude(
        f"analytics_script_{payload.slot}",
        _MODEL,
        msg.usage.input_tokens,
        msg.usage.output_tokens,
    )

    raw = msg.content[0].text.strip()
    script_body, hook_visual, edge_summary = _parse_response(raw, payload)

    return AnalyticsScript(
        game_id=payload.game.game_id,
        slot=payload.slot,
        home_team=payload.game.home_team,
        away_team=payload.game.away_team,
        game_time_utc=payload.game.start_time_utc.isoformat(),
        script_body=script_body,
        hook_visual=hook_visual,
        edge_summary=edge_summary,
        model_snapshot={
            "home_win_prob": payload.poisson.home_win_prob,
            "away_win_prob": payload.poisson.away_win_prob,
            "expected_total": payload.poisson.expected_total,
            "calibration_version": payload.poisson.calibration_version,
        },
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Prompt builders (one per slot)
# ---------------------------------------------------------------------------

def _build_prompt(payload: AnalyticsPayload) -> str:
    if payload.slot == "preview":
        return _prompt_preview(payload)
    if payload.slot == "pre":
        return _prompt_pre(payload)
    return _prompt_post(payload)


def _prompt_preview(p: AnalyticsPayload) -> str:
    e, po = p.edge, p.poisson
    game_date = p.game.start_time_utc.strftime("%B %d")
    return (
        f"Game: {p.game.away_team} @ {p.game.home_team} on {game_date}\n\n"
        f"Model output:\n"
        f"- Home win probability: {po.home_win_prob:.1%}\n"
        f"- Away win probability: {po.away_win_prob:.1%}\n"
        f"- Expected total goals: {po.expected_total:.2f}\n"
        f"- Moneyline edge on home: {e.moneyline_edge:+.1%}\n"
        f"- Market total line: {e.market_total_line or 'N/A'}\n"
        f"- Home moneyline: {e.market_home_implied_prob:.1%} implied\n\n"
        "Write a PREVIEW script. Focus: team matchup, win probability, model edge."
    )


def _prompt_pre(p: AnalyticsPayload) -> str:
    e, po = p.edge, p.poisson
    picks_lines = "\n".join(
        f"  - {pp.player_name} ({pp.team}): {pp.goal_prob:.1%} goal prob, "
        f"expected {pp.expected_goals:.2f} goals"
        for pp in p.player_picks
    )
    return (
        f"Game: {p.game.away_team} @ {p.game.home_team} — TODAY\n\n"
        f"Team model:\n"
        f"- Home win probability: {po.home_win_prob:.1%}\n"
        f"- Moneyline edge on home: {e.moneyline_edge:+.1%}\n"
        f"- Expected total: {po.expected_total:.2f} vs market line {e.market_total_line or 'N/A'}\n\n"
        f"Top goal scorer picks:\n{picks_lines}\n\n"
        "Write a PRE-GAME script. Focus: player props, who scores tonight."
    )


def _prompt_post(p: AnalyticsPayload) -> str:
    e = p.edge
    snap = p.model_snapshot or {}
    r = p.actual_result

    actual_winner = (
        "Home win" if r and r.home_score > r.away_score
        else "Away win" if r and r.away_score > r.home_score
        else "Unknown"
    )
    actual_total = (r.home_score + r.away_score) if r else "?"
    final_str = (
        f"{r.away_score}-{r.home_score} {r.final_period}" if r else "result unknown"
    )

    return (
        f"Game: {p.game.away_team} @ {p.game.home_team} — FINAL: {final_str}\n\n"
        f"What we predicted:\n"
        f"- Home win probability: {snap.get('home_win_prob', p.poisson.home_win_prob):.1%}\n"
        f"- Expected total goals: {snap.get('expected_total', p.poisson.expected_total):.2f}\n"
        f"- Moneyline edge on home: {e.moneyline_edge:+.1%}\n\n"
        f"What happened: {actual_winner}, {actual_total} total goals\n\n"
        "Write a POST-GAME script. Focus: model accuracy, what was right/wrong and why."
    )


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_response(
    raw: str,
    payload: AnalyticsPayload,
) -> tuple[str, str, str]:
    """Extract (script_body, hook_visual, edge_summary) from Claude's output."""
    script_body = raw
    hook_visual = ""
    edge_summary = ""

    # Try to split off trailing JSON block
    for delimiter in ("{\"hook_visual\"", '{"hook_visual"'):
        if delimiter in raw:
            idx = raw.index(delimiter)
            script_body = raw[:idx].strip()
            try:
                meta = json.loads(raw[idx:])
                hook_visual = meta.get("hook_visual", "")
                edge_summary = meta.get("edge_summary", "")
                return script_body, hook_visual, edge_summary
            except json.JSONDecodeError:
                pass

    # Fallback: derive from payload
    e = payload.edge
    direction = "home" if e.moneyline_edge > 0 else "away"
    edge_summary = f"{e.moneyline_edge:+.1%} edge on {direction} moneyline"
    hook_visual = f"{payload.game.away_team} @ {payload.game.home_team} analytics"
    return script_body, hook_visual, edge_summary


def _anthropic_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set in environment")
    return key
