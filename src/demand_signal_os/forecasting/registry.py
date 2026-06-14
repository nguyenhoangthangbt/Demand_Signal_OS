"""Forecaster registry — the factory the leaderboard orchestrates over.

Maps a ``method_id`` to a builder that constructs a ``ForecastMethod`` from
a ``LeaderboardConfig``. This is the missing layer that turns DSO's fixed
set of forecasters into a runtime-selectable panel without an AutoML search:
the registry only ever instantiates the engine's own audited methods, with
the four user knobs threaded through.

Method groups:
- FORECASTER_IDS : the candidate models that compete for the winner slot.
- BENCHMARK_IDS  : the mandatory naive floor (CONSTITUTION §5). Always run;
  a forecaster must beat ALL of them on CRPS to be production-trustworthy.
- INTERMITTENT_IDS: included when the series is intermittent (auto-detected
  or forced on), excluded when forced off.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from demand_signal_os.backtest.benchmarks import (
    MovingAverageMethod,
    NaiveSeasonalMethod,
    SESMethod,
)
from demand_signal_os.forecasting.ets import ETSMethod
from demand_signal_os.forecasting.gbm import GBMQuantileMethod
from demand_signal_os.forecasting.intermittent.stubs import (
    CrostonOptimizedMethod,
    CrostonSBAMethod,
    TSBMethod,
)
from demand_signal_os.forecasting.protocol import ForecastMethod
from demand_signal_os.leaderboard.types import LeaderboardConfig

# Threshold above which a series is treated as intermittent (zero fraction).
INTERMITTENT_ZERO_FRACTION = 0.30

BENCHMARK_IDS: tuple[str, ...] = ("naive_seasonal", "ses", "moving_average")
INTERMITTENT_IDS: tuple[str, ...] = ("croston_opt", "tsb", "sba")
# Continuous-demand forecasters always in the panel.
CONTINUOUS_FORECASTER_IDS: tuple[str, ...] = ("ets", "gbm")

# Builders: method_id -> (config -> ForecastMethod). Each threads the four
# user knobs; engine-internal hyperparameters stay at audited defaults.
_BUILDERS: dict[str, Callable[[LeaderboardConfig], ForecastMethod]] = {
    "ets": lambda c: ETSMethod(
        season_length=c.season_length, min_quantile_spread=c.min_quantile_spread
    ),
    "gbm": lambda c: GBMQuantileMethod(min_quantile_spread=c.min_quantile_spread),
    "croston_opt": lambda c: CrostonOptimizedMethod(
        min_quantile_spread=c.min_quantile_spread
    ),
    "tsb": lambda c: TSBMethod(min_quantile_spread=c.min_quantile_spread),
    "sba": lambda c: CrostonSBAMethod(min_quantile_spread=c.min_quantile_spread),
    "naive_seasonal": lambda c: NaiveSeasonalMethod(season_length=c.season_length),
    "ses": lambda c: SESMethod(),
    "moving_average": lambda c: MovingAverageMethod(),
}

REGISTERED_IDS: tuple[str, ...] = tuple(_BUILDERS.keys())


def build_method(method_id: str, config: LeaderboardConfig) -> ForecastMethod:
    """Instantiate a registered ForecastMethod for the given config."""
    try:
        return _BUILDERS[method_id](config)
    except KeyError:
        raise KeyError(
            f"unknown method_id {method_id!r}; registered: {REGISTERED_IDS}"
        ) from None


def is_intermittent(history: list[float]) -> bool:
    """Heuristic: a series is intermittent if >=30% of buckets are zero."""
    if not history:
        return False
    arr = np.asarray(history, dtype=float)
    zero_fraction = float(np.mean(arr == 0.0))
    return zero_fraction >= INTERMITTENT_ZERO_FRACTION


def select_method_ids(history: list[float], config: LeaderboardConfig) -> list[str]:
    """Pick which methods compete, given the series and the intermittent knob.

    Benchmarks always run (the gate). Continuous forecasters always run.
    Intermittent forecasters run when mode is 'on', or 'auto' + detected.
    Order is deterministic for reproducible content hashing.
    """
    ids: list[str] = list(CONTINUOUS_FORECASTER_IDS)

    include_intermittent = config.intermittent_mode == "on" or (
        config.intermittent_mode == "auto" and is_intermittent(history)
    )
    if include_intermittent:
        ids.extend(INTERMITTENT_IDS)

    ids.extend(BENCHMARK_IDS)
    return ids
