# AnalyticsBot — Codebase Guide

## What this project does
Sports analytics pipeline that generates YouTube Shorts scripts — win probabilities,
betting edge vs market, player goal predictions — then grades predictions post-game.

**Brand promise:** Surface the number the betting line missed, before every big game.

Phase 1: NHL playoffs. Phase 2: NBA Finals (June 3). Phase 3: FIFA World Cup (June 11).
Same pipeline, same 5-beat format — only the data module and model variant change per sport.

Runs via Windows Task Scheduler, orchestrated daily by `schedule_today.py`.

## Running the pipeline
```bash
python pipeline.py --slot preview               # D-1 team matchup (or next game if no game today)
python pipeline.py --slot pre --game-id X       # 6h before game: player prop predictions
python pipeline.py --slot post --game-id X      # 2h after game: model vs reality recap
python schedule_today.py                        # register today's schtasks (runs at 6am)
```

## Content slots
| Slot | Trigger | Content |
|---|---|---|
| `preview` | No game today — runs immediately for next upcoming game | Team matchup, win probability, D-1 edge |
| `pre` | game_start − 6h | Player goal scorer odds, who scores tonight |
| `post` | estimated_end + 2h | Model vs reality — what the numbers got right |

## Key files
| File | Purpose |
|---|---|
| `pipeline.py` | Orchestrator: --slot preview\|pre\|post --game-id --sport |
| `schedule_today.py` | 6am daily: NHL schedule → schtasks entries |
| `data/nhl_schedule.py` | NHL public API → NHLGame, GameResult |
| `data/moneypuck.py` | MoneyPuck CSV → TeamStats, PlayerStats |
| `data/odds.py` | The Odds API → GameOdds, PlayerOdds |
| `models/poisson.py` | Poisson goals model (shots × (1 − sv_pct)); user's prototype |
| `models/team_model.py` | TeamStats → PoissonResult via poisson.run() |
| `models/player_model.py` | PlayerStats → PlayerPoissonResult via _poisson_pmf_list() |
| `models/edge.py` | PoissonResult + GameOdds → BettingEdge, game selection |
| `models/calibration/historical.py` | Returns identity calibration today; seam for future backtesting |
| `scripts/generator.py` | Claude script generation (5-beat, 40–45 sec) |
| `history/game_state.py` | Tracks which slots have run per game (idempotent) |
| `costs/tracker.py` | Logs Claude usage to costs/usage_YYYY-MM-DD.jsonl |

## Poisson model
`models/poisson.py` contains the user's shots-based Poisson model verbatim.
Lambda formula: `lam = team_shot_rate_60 × (1 − opponent_save_pct)`
Key note on `opp_goalie_sv_pct` in TeamInputs: set to THIS team's own goalie save_pct.
`poisson.run()` uses `lam_home = home.shots × (1 − away.opp_goalie_sv_pct)`, so
away.opp_goalie_sv_pct must equal the away goalie's save_pct for the math to work out.

## Win probability semantics
`calculate_win_probabilities()` returns `(home_win, ot_prob, away_win)`:
- `home_win + away_win = 1.0` — OT-adjusted, normalized
- `ot_prob` = raw probability of reaching overtime — bonus info, not a third outcome
This means `home_win + ot_prob + away_win > 1.0` — that's expected and correct.

## Data sources
- **NHL schedule + results**: `https://api-web.nhle.com/v1/` (free, no key)
- **MoneyPuck stats**: `https://moneypuck.com/moneypuck/playerData/seasonSummary/{year}/regular/teams.csv`
- **The Odds API**: `icehockey_nhl` moneyline + totals (ODDS_API_KEY, 500 req/mo free)

## Testing
```bash
python -m pytest tests/unit/ -q        # 149 unit tests, no API calls, ~1s
python -m pytest tests/e2e/ -v         # 16 e2e tests, all APIs mocked
python -m pytest -q                    # all 165 tests
```

## Git workflow
- Work on `dev`, merge to `master` only after tests pass
- Task Scheduler runs from `master`
- No changes to ShortsBot or YT-Responder — self-contained

## Environment
Create `AnalyticsBot/.env` from `.env.example`:
- `ANTHROPIC_API_KEY` — shared with ShortsBot
- `ODDS_API_KEY` — The Odds API key
- `ANALYTICS_YT_CHANNEL_ID` — once the Analytics channel is created
- `ANALYTICS_YT_CLIENT_SECRET_FILE` — once upload is wired

## Future work
- Calibrate Poisson model against historical NHL data (`models/calibration/historical.py`)
- Wire ShortsBot TTS + video assembly for full video production
- Phase 2 NBA: `data/nba_schedule.py` + `data/nba_stats.py` + `models/nba_team_model.py`
- QA agent (GATE-3 equivalent)
