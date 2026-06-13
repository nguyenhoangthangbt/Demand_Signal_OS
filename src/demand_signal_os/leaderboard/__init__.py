"""Forecaster leaderboard — ML-capability layer for the Enterprise e2e bundle.

Public surface:
- ``LeaderboardConfig`` / ``LeaderboardEntry`` / ``LeaderboardResult`` — contracts.
- ``orchestrate(actuals, config)`` — run + rank + gate + pick winner.
"""

from __future__ import annotations

from demand_signal_os.leaderboard.orchestrator import orchestrate
from demand_signal_os.leaderboard.types import (
    CANONICAL_QUANTILES,
    LeaderboardConfig,
    LeaderboardEntry,
    LeaderboardResult,
)

__all__ = [
    "CANONICAL_QUANTILES",
    "LeaderboardConfig",
    "LeaderboardEntry",
    "LeaderboardResult",
    "orchestrate",
]
