"""
Calibration layer — placeholder for future historical backtesting.

Today this returns identity multipliers (no correction applied).

When ready to calibrate:
1. Load historical NHL game data (e.g., from hockey-reference or NHL API)
2. Compare raw Poisson predictions against actual results
3. Compute Brier scores and calibration curves
4. Fit correction factors and store them in a JSON file or DB
5. Load and return them here

team_model.py and player_model.py both call get_calibration_factors() before
returning their predictions — update only this file to apply calibration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CalibrationFactors:
    team_goal_multiplier: float = 1.0
    player_goal_multiplier: float = 1.0
    version: str = "uncalibrated_v0"


def get_calibration_factors(season: str | None = None) -> CalibrationFactors:
    """
    Return calibration factors for *season* (e.g. "20252026").
    Returns identity (no correction) until historical data is wired in.
    """
    return CalibrationFactors()
