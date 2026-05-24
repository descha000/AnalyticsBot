"""
Calibration layer — applies empirical correction factors by game type.

Playoff calibration (v0):
  NHL playoffs average ~5.5-5.8 total goals/game vs ~6.1 in the regular season.
  Factor 0.90 was chosen empirically to bring model output into that range.
  Replace with backtested values once we accumulate prediction vs result data.

When ready to improve calibration:
1. Load historical game data (from NHL API or hockey-reference)
2. Compare raw Poisson predictions against actual results
3. Compute Brier scores and calibration curves
4. Fit correction factors per season and game type
5. Store in a JSON file and load them here
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CalibrationFactors:
    team_goal_multiplier: float = 1.0
    player_goal_multiplier: float = 1.0
    version: str = "uncalibrated_v0"


def get_calibration_factors(
    season: str | None = None,
    game_type: str = "regular",
) -> CalibrationFactors:
    """
    Return calibration factors for *season* and *game_type*.

    game_type : "regular" | "playoff"
        Playoff games are calibrated down from regular-season rates.
    """
    if game_type == "playoff":
        return CalibrationFactors(
            team_goal_multiplier=0.90,
            player_goal_multiplier=0.90,
            version="playoff_empirical_v0",
        )
    return CalibrationFactors()
