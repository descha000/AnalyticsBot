"""Shared fixtures for all tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data.moneypuck import PlayerStats, TeamStats
from data.nhl_schedule import GameResult, NHLGame
from data.odds import GameOdds
from models.edge import BettingEdge
from models.player_model import PlayerPoissonResult
from models.team_model import PoissonResult


@pytest.fixture
def boston_game() -> NHLGame:
    return NHLGame(
        game_id="2025030401",
        home_team="BOS",
        away_team="FLA",
        start_time_utc=datetime(2026, 5, 23, 23, 0, tzinfo=timezone.utc),
        estimated_end_utc=datetime(2026, 5, 24, 1, 45, tzinfo=timezone.utc),
        season="20252026",
        game_type="playoff",
    )


@pytest.fixture
def boston_stats() -> TeamStats:
    return TeamStats(
        team="BOS",
        xgf_per_game=2.95,
        xga_per_game=2.50,
        shot_rate_60=31.2,
        save_pct=0.912,
        pp_pct=0.225,
        pk_pct=0.838,
        games_played=82,
    )


@pytest.fixture
def florida_stats() -> TeamStats:
    return TeamStats(
        team="FLA",
        xgf_per_game=2.70,
        xga_per_game=2.60,
        shot_rate_60=29.5,
        save_pct=0.905,
        pp_pct=0.198,
        pk_pct=0.821,
        games_played=82,
    )


@pytest.fixture
def sample_player() -> PlayerStats:
    return PlayerStats(
        player_id="8478402",
        player_name="David Pastrnak",
        team="BOS",
        position="R",
        shots_per_60=3.8,
        shooting_pct=0.155,
        toi_per_game=19.5,
        games_played=72,
    )


@pytest.fixture
def boston_odds() -> GameOdds:
    return GameOdds(
        game_id="2025030401",
        odds_event_id="event_abc",
        home_team="BOS",
        away_team="FLA",
        home_moneyline=-145,
        away_moneyline=122,
        home_implied_prob=0.5450,
        away_implied_prob=0.4550,
        total_line=5.5,
        book="draftkings",
    )


@pytest.fixture
def sample_poisson() -> PoissonResult:
    return PoissonResult(
        home_team="BOS",
        away_team="FLA",
        home_win_prob=0.5200,
        draw_prob=0.1800,
        away_win_prob=0.3000,
        expected_home_goals=2.95,
        expected_away_goals=2.50,
        expected_total=5.45,
        calibration_version="uncalibrated_v0",
    )


@pytest.fixture
def sample_edge(sample_poisson, boston_odds) -> BettingEdge:
    from models.edge import compute_edge
    return compute_edge(sample_poisson, boston_odds)


@pytest.fixture
def final_result() -> GameResult:
    return GameResult(
        game_id="2025030401",
        home_score=3,
        away_score=2,
        went_to_ot=False,
        final_period="REG",
    )
