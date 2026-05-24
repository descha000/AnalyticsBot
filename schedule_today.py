"""
Daily task scheduler for AnalyticsBot.

Run at 6:00 AM via Windows Task Scheduler.
Fetches today's NHL schedule and registers schtasks entries for each game:
  - pre  slot at game_start − 6 hours
  - post slot at estimated_end + 2 hours

If no games today, runs the preview slot immediately for the next upcoming game.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from data.nhl_schedule import fetch_next_game, fetch_today_games

# Absolute paths so schtasks can find them regardless of working directory
_VENV_PYTHON = str(
    Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
)
_PIPELINE = str(Path(__file__).parent / "pipeline.py")
_TASK_FOLDER = "AnalyticsBot"


def main() -> None:
    games = fetch_today_games()

    if games:
        now = datetime.now(timezone.utc)
        registered = 0
        for game in games:
            pre_time = game.start_time_utc - timedelta(hours=6)
            post_time = game.estimated_end_utc + timedelta(hours=2)

            if pre_time > now:
                _register(f"pre_{game.game_id}", pre_time, "pre", game.game_id)
                registered += 1
            else:
                print(f"[schedule] pre_{game.game_id}: start time already passed, skipping")

            if post_time > now:
                _register(f"post_{game.game_id}", post_time, "post", game.game_id)
                registered += 1

        print(f"[schedule] {len(games)} game(s) today — {registered} task(s) registered")

    else:
        next_game = fetch_next_game()
        if not next_game:
            print("[schedule] No games today or upcoming — nothing to do")
            return

        print(
            f"[schedule] No games today — generating preview for next game: "
            f"{next_game.away_team} @ {next_game.home_team}"
        )
        subprocess.run(
            [_VENV_PYTHON, _PIPELINE, "--slot", "preview", "--game-id", next_game.game_id],
            check=True,
        )


def _register(task_name: str, run_time: datetime, slot: str, game_id: str) -> None:
    local = run_time.astimezone()
    time_str = local.strftime("%H:%M")
    date_str = local.strftime("%m/%d/%Y")
    cmd = f'"{_VENV_PYTHON}" "{_PIPELINE}" --slot {slot} --game-id {game_id}'

    subprocess.run(
        [
            "schtasks", "/Create", "/F",
            "/TN", f"{_TASK_FOLDER}\\{task_name}",
            "/TR", cmd,
            "/SC", "ONCE",
            "/ST", time_str,
            "/SD", date_str,
        ],
        check=True,
    )
    print(f"[schedule] registered {task_name} at {time_str} on {date_str}")


if __name__ == "__main__":
    main()
