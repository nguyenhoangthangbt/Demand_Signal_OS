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
from typing import TYPE_CHECKING

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
from demand_signal_os.forecasting.statistical import (
    AutoARIMAMethod,
    AutoCESMethod,
    AutoThetaMethod,
)

if TYPE_CHECKING:
    # Type-only import — avoids a runtime cycle (leaderboard.* imports registry).
    # The builders use the config via duck typing, so the class isn't needed
    # at runtime.
    from demand_signal_os.leaderboard.types import LeaderboardConfig

# Threshold above which a series is treated as intermittent (zero fraction).
INTERMITTENT_ZERO_FRACTION = 0.30

BENCHMARK_IDS: tuple[str, ...] = ("naive_seasonal", "ses", "moving_average")
INTERMITTENT_IDS: tuple[str, ...] = ("croston_opt", "tsb", "sba")
# Continuous-demand forecasters always in the panel. Expanded 2026-06-14 with
# the M-competition statistical trio (arima/theta/ces) alongside ets + gbm.
CONTINUOUS_FORECASTER_IDS: tuple[str, ...] = ("ets", "gbm", "arima", "theta", "ces")

# Forecaster classes (for the forecaster_set selector). Benchmarks are NOT a
# selectable class — they always run as the gate.
STATISTICAL_IDS: tuple[str, ...] = ("ets", "arima", "theta", "ces")
ML_IDS: tuple[str, ...] = ("gbm",)
FAST_IDS: tuple[str, ...] = ("ets", "theta")  # cheapest fits — quick scan
# Canonical order for deterministic explicit-methods selection.
_ALL_FORECASTER_IDS: tuple[str, ...] = (*CONTINUOUS_FORECASTER_IDS, *INTERMITTENT_IDS)

# Builders: method_id -> (config -> ForecastMethod). Each threads the four
# user knobs; engine-internal hyperparameters stay at audited defaults.
_BUILDERS: dict[str, Callable[[LeaderboardConfig], ForecastMethod]] = {
    "ets": lambda c: ETSMethod(
        season_length=c.season_length, min_quantile_spread=c.min_quantile_spread
    ),
    "gbm": lambda c: GBMQuantileMethod(min_quantile_spread=c.min_quantile_spread),
    "arima": lambda c: AutoARIMAMethod(
        season_length=c.season_length, min_quantile_spread=c.min_quantile_spread
    ),
    "theta": lambda c: AutoThetaMethod(
        season_length=c.season_length, min_quantile_spread=c.min_quantile_spread
    ),
    "ces": lambda c: AutoCESMethod(
        season_length=c.season_length, min_quantile_spread=c.min_quantile_spread
    ),
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
    """Pick which methods compete, given the series and the panel-focus knobs.

    Selection precedence:
      1. ``config.methods`` (explicit allowlist) — exactly those forecasters.
      2. ``config.forecaster_set`` class — that class only ("all"/"full" run
         the full panel + intermittent per ``intermittent_mode``).
    Benchmarks ALWAYS run (the beats-naive gate); they are never selectable
    away. Order is deterministic for reproducible content hashing.
    """
    methods = getattr(config, "methods", None)
    if methods:
        unknown = [m for m in methods if m not in _ALL_FORECASTER_IDS]
        if unknown:
            raise ValueError(
                f"unknown forecaster(s) {unknown}; choose from {_ALL_FORECASTER_IDS}"
            )
        chosen = set(methods)
        ids = [m for m in _ALL_FORECASTER_IDS if m in chosen]  # canonical order
        ids.extend(BENCHMARK_IDS)
        return ids

    fset = getattr(config, "forecaster_set", "all")
    if fset in ("all", "full"):
        ids = list(CONTINUOUS_FORECASTER_IDS)
        include_intermittent = config.intermittent_mode == "on" or (
            config.intermittent_mode == "auto" and is_intermittent(history)
        )
        if include_intermittent:
            ids.extend(INTERMITTENT_IDS)
    elif fset == "statistical":
        ids = list(STATISTICAL_IDS)
    elif fset == "ml":
        ids = list(ML_IDS)
    elif fset == "intermittent":
        ids = list(INTERMITTENT_IDS)
    elif fset == "fast":
        ids = list(FAST_IDS)
    else:  # defensive — Literal should prevent this
        raise ValueError(f"unknown forecaster_set {fset!r}")

    ids.extend(BENCHMARK_IDS)
    return ids
