# AnalyticsBot — Codebase Guide

## What this project does
NHL (and future NBA) analytics pipeline that generates YouTube Shorts scripts
built on a Poisson goals model, MoneyPuck advanced stats, and The Odds API.

Runs via Windows Task Scheduler, scheduled daily by `schedule_today.py`.

## Running the pipeline
```bash
python pipeline.py --slot preview               # D-1 team matchup (or next game if no game today)
python pipeline.py --slot pre --game-id X       # 6h before game: player prop predictions
python pipeline.py --slot post --game-id X      # 2h after game: model vs reality recap
python pipeline.py --slot pre --sport nba       # NBA (future)
python schedule_today.py                        # register today's schtasks (run at 6am)
```

## Content types
| Slot | Trigger | Content |
|---|---|---|
| `preview` | If no game today, or eve before game day | Team matchup, win probability |
| `pre` | game_start − 6h | Player goal scorer odds, prop predictions |
| `post` | estimated_end + 2h | Model vs reality — what was right/wrong and why |

## Key files
| File | Purpose |
|---|---|
| `pipeline.py` | Orchestrator: --slot preview\|pre\|post --game-id --sport |
| `schedule_today.py` | 6am daily: NHL schedule → schtasks entries |
| `data/nhl_schedule.py` | NHL public API → NHLGame, GameResult |
| `data/moneypuck.py` | MoneyPuck CSV → TeamStats, PlayerStats |
| `data/odds.py` | The Odds API → GameOdds, PlayerOdds |
| `models/poisson.py` | Poisson goals calculator (paste your prototype here) |
| `models/team_model.py` | TeamStats → PoissonResult |
| `models/player_model.py` | PlayerStats → PlayerPoissonResult |
| `models/edge.py` | PoissonResult + GameOdds → BettingEdge, game selection |
| `models/calibration/historical.py` | FUTURE calibration; returns identity today |
| `scripts/generator.py` | Claude script generation (5-beat, 40-45 sec) |
| `history/game_state.py` | Tracks which slots have run per game |
| `costs/tracker.py` | Logs Claude usage to costs/usage_YYYY-MM-DD.jsonl |

## Model: your Poisson prototype
Drop your implementation into `models/poisson.py`.
The function signature that must be preserved:
```python
def calculate_win_probabilities(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 10,
) -> tuple[float, float, float]:
    ...  # returns (home_win_prob, draw_prob, away_win_prob)
```

## Data sources
- **NHL schedule + results**: `https://api-web.nhle.com/v1/` (free, no key)
- **MoneyPuck stats**: `https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/teams.csv` (free CSV, re-fetched daily)
- **The Odds API**: moneyline + player props (ODDS_API_KEY, 500 req/mo free tier)

## MoneyPuck column names (verify if CSV format changes)
Teams: `team`, `situation`, `iceTime`, `xGoalsFor`, `xGoalsAgainst`,
       `goalsAgainst`, `shotsOnGoalFor`, `shotsOnGoalAgainst`, `gamesPlayed`
Skaters: `playerId`, `name`, `team`, `position`, `situation`, `games_played`,
         `icetime`, `I_F_goals`, `I_F_shotsOnGoal`

## Testing
```bash
python -m pytest tests/unit/ -q              # unit tests, no API calls, fast
python -m pytest tests/e2e/ -m e2e -v        # e2e tests, all APIs mocked
python -m pytest -q                          # all tests
```

## Git workflow
- Work on `dev`, merge to `master` only after tests pass
- Task Scheduler runs from `master`
- No changes to ShortsBot or YT-Responder — this project is fully self-contained

## Environment
Add to `AnalyticsBot/.env`:
- `ANTHROPIC_API_KEY` (shared with ShortsBot)
- `ODDS_API_KEY`
- `ANALYTICS_YT_CHANNEL_ID` (once channel is created)
- `ANALYTICS_YT_CLIENT_SECRET_FILE`

## Future work
- Calibrate Poisson model against historical NHL data (`models/calibration/historical.py`)
- Wire ShortsBot TTS + video assembly for full video production
- NBA pivot: swap `data/nhl_schedule.py` → `data/nba_schedule.py`, add NBA stats source
- QA agent (GATE-3 equivalent) for video quality
