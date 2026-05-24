"""
AnalyticsBot pipeline orchestrator.

Usage:
  python pipeline.py --slot preview               # D-1 team matchup (next game if no game today)
  python pipeline.py --slot pre --game-id X       # player props, 6h before game
  python pipeline.py --slot post --game-id X      # model vs reality, 2h after game
  python pipeline.py --slot pre --sport nba       # future NBA support
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from data.moneypuck import fetch_player_stats, fetch_team_stats
from data.nhl_schedule import NHLGame, fetch_game_result, fetch_next_game, fetch_today_games
from data.odds import fetch_game_odds, fetch_player_odds, match_odds_to_games
from history.game_state import (
    get_model_snapshot,
    is_slot_done,
    mark_slot_done,
    save_model_snapshot,
)
from models.edge import BettingEdge, compute_edge, select_featured_game
from models.player_model import top_goal_scorers
from models.team_model import run_team_model
from scripts.generator import AnalyticsPayload, generate_script

OUTPUT_DIR = Path(__file__).parent / "output"

_SPORT_KEYS = {
    "nhl": "icehockey_nhl",
    "nba": "basketball_nba",
}


def run_preview(game: NHLGame, sport: str) -> None:
    game_id = game.game_id
    if is_slot_done(game_id, "preview"):
        print(f"[pipeline] preview already done for {game_id}, skipping")
        return

    home_stats, away_stats = _fetch_team_stats(game)
    poisson = run_team_model(home_stats, away_stats)

    odds = _fetch_odds_for_game(game, sport)

    edge = compute_edge(poisson, odds)
    payload = AnalyticsPayload(
        game=game, slot="preview", edge=edge, poisson=poisson,
        player_picks=[], actual_result=None, model_snapshot=None,
    )
    script = generate_script(payload)
    _write_output(script)
    save_model_snapshot(game_id, script.model_snapshot)
    mark_slot_done(game_id, "preview")
    print(f"[pipeline] preview done — {game.away_team} @ {game.home_team}")


def run_pre(game: NHLGame, sport: str) -> None:
    game_id = game.game_id
    if is_slot_done(game_id, "pre"):
        print(f"[pipeline] pre already done for {game_id}, skipping")
        return

    home_stats, away_stats = _fetch_team_stats(game)
    poisson = run_team_model(home_stats, away_stats)

    odds = _fetch_odds_for_game(game, sport)
    edge = compute_edge(poisson, odds)

    all_players = fetch_player_stats()
    home_picks = top_goal_scorers(all_players, game.home_team, top_n=2)
    away_picks = top_goal_scorers(all_players, game.away_team, top_n=1)

    payload = AnalyticsPayload(
        game=game, slot="pre", edge=edge, poisson=poisson,
        player_picks=home_picks + away_picks,
        actual_result=None, model_snapshot=None,
    )
    script = generate_script(payload)
    _write_output(script)
    save_model_snapshot(game_id, script.model_snapshot)
    mark_slot_done(game_id, "pre")
    print(f"[pipeline] pre done — {game.away_team} @ {game.home_team}")


def run_post(game: NHLGame, sport: str) -> None:
    game_id = game.game_id
    if is_slot_done(game_id, "post"):
        print(f"[pipeline] post already done for {game_id}, skipping")
        return

    result = fetch_game_result(game_id)
    if not result:
        print(f"[pipeline] Game {game_id} not final yet — try again later")
        sys.exit(0)

    home_stats, away_stats = _fetch_team_stats(game)
    poisson = run_team_model(home_stats, away_stats)

    odds = _fetch_odds_for_game(game, sport)
    edge = compute_edge(poisson, odds)

    snapshot = get_model_snapshot(game_id)

    payload = AnalyticsPayload(
        game=game, slot="post", edge=edge, poisson=poisson,
        player_picks=[], actual_result=result, model_snapshot=snapshot,
    )
    script = generate_script(payload)
    _write_output(script)
    mark_slot_done(game_id, "post")
    print(
        f"[pipeline] post done — {game.away_team} @ {game.home_team} "
        f"({result.away_score}-{result.home_score} {result.final_period})"
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fetch_team_stats(game: NHLGame):
    all_stats = fetch_team_stats()
    home = all_stats.get(game.home_team)
    away = all_stats.get(game.away_team)
    if not home or not away:
        print(
            f"[pipeline] Missing MoneyPuck stats for "
            f"{game.home_team} or {game.away_team}"
        )
        sys.exit(1)
    return home, away


def _fetch_odds_for_game(game: NHLGame, sport: str):
    sport_key = _SPORT_KEYS.get(sport, sport)
    all_odds = fetch_game_odds(sport=sport_key)
    matched = match_odds_to_games([game], all_odds)
    odds = matched.get(game.game_id)
    if not odds:
        print(f"[pipeline] No odds found for {game.game_id} ({game.away_team} @ {game.home_team})")
        sys.exit(1)
    return odds


def _write_output(script) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"{script.game_id}_{script.slot}.json"
    path.write_text(json.dumps(asdict(script), indent=2), encoding="utf-8")
    print(f"[pipeline] script → {path}")


def _resolve_game(game_id: str | None, slot: str) -> NHLGame:
    games = fetch_today_games()

    if game_id:
        for g in games:
            if g.game_id == game_id:
                return g
        print(f"[pipeline] game_id {game_id} not found in today's schedule")
        sys.exit(1)

    if slot == "preview":
        game = fetch_next_game()
        if not game:
            print("[pipeline] No upcoming games found in the next 7 days — nothing to do")
            sys.exit(0)
        return game

    if not games:
        print("[pipeline] No games today and slot is not 'preview' — nothing to do")
        sys.exit(0)

    return games[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AnalyticsBot pipeline")
    parser.add_argument(
        "--slot", choices=["preview", "pre", "post"], required=True,
        help="Content type to generate",
    )
    parser.add_argument(
        "--game-id", default=None,
        help="NHL game ID (optional; defaults to first game today / next game for preview)",
    )
    parser.add_argument(
        "--sport", default="nhl", choices=["nhl", "nba"],
        help="Sport (default: nhl)",
    )
    args = parser.parse_args()

    game = _resolve_game(args.game_id, args.slot)

    if args.slot == "preview":
        run_preview(game, args.sport)
    elif args.slot == "pre":
        run_pre(game, args.sport)
    else:
        run_post(game, args.sport)
