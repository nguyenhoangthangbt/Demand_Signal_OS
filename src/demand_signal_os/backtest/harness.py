"""Walk-forward backtest harness per BACKTESTING.md §2.

M5-aligned rolling-origin evaluation:
- min 4 windows operational/tactical, 2 strategic
- frozen historical cuts via data_cut_timestamp
- strictly no lookahead
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import numpy as np

from demand_signal_os.backtest.metrics import crps, pinball_loss, smape, wis
from demand_signal_os.forecasting.protocol import ForecastMethod, ForecastRequest
from demand_signal_os.ops_schemas import DemandActual, ForecastBundle, TimeBucket


@dataclass
class BacktestWindow:
    """One walk-forward window."""

    window_index: int
    train_size: int
    horizon_size: int
    data_cut_timestamp: datetime


@dataclass
class WindowResult:
    """Per-window per-method scoring output."""

    window_index: int
    method_id: str
    sku_id: str
    location_id: str
    bucket: TimeBucket
    actual: float
    forecast_mean: float
    smape: float | None
    crps: float
    pinball_q50: float
    pinball_q90: float
    wis: float


@dataclass
class BacktestSummary:
    """Aggregate per-method scoring across windows."""

    method_id: str
    n_windows: int
    mean_crps: float
    mean_smape: float | None
    mean_pinball_q50: float
    mean_pinball_q90: float
    mean_wis: float
    beats_all_benchmarks: bool | None = None


def make_windows(
    history_length: int,
    *,
    n_windows: int,
    horizon_size: int,
    min_train_size: int,
) -> list[BacktestWindow]:
    """Construct non-overlapping rolling-origin windows.

    Last window's train ends just before the last `horizon_size` records;
    earlier windows step back by `horizon_size` each.
    """
    if n_windows < 1:
        raise ValueError("n_windows must be >= 1")
    if history_length < min_train_size + horizon_size:
        raise ValueError(
            f"history_length {history_length} too small for "
            f"min_train_size {min_train_size} + horizon_size {horizon_size}"
        )
    windows: list[BacktestWindow] = []
    last_train_end = history_length - horizon_size
    for w in range(n_windows):
        train_end = last_train_end - w * horizon_size
        if train_end < min_train_size:
            break
        windows.append(
            BacktestWindow(
                window_index=w,
                train_size=train_end,
                horizon_size=horizon_size,
                data_cut_timestamp=datetime.now(timezone.utc),
            )
        )
    return list(reversed(windows))  # chronological order


def evaluate_window(
    method: ForecastMethod,
    actuals: list[DemandActual],
    history_values_full: list[float],
    window: BacktestWindow,
    *,
    horizon_label: Literal["operational", "tactical", "strategic"] = "operational",
    seed: int = 42,
) -> list[WindowResult]:
    """Score one method on one window across all horizon buckets.

    Caller's actuals + history_values_full are the FULL series. The window
    selects the train slice and the horizon slice.
    """
    train = history_values_full[: window.train_size]
    horizon_records = actuals[window.train_size : window.train_size + window.horizon_size]
    if len(horizon_records) != window.horizon_size:
        raise ValueError("window horizon doesn't fit within actuals")

    results: list[WindowResult] = []
    for k, actual_record in enumerate(horizon_records):
        request = ForecastRequest(
            sku_id=actual_record.sku_id,
            location_id=actual_record.location_id,
            history=train + [r.units_sold for r in horizon_records[:k]],
            history_buckets=[],
            horizon_buckets=[actual_record.bucket],
            horizon_label=horizon_label,
            seed=seed,
            data_cut_timestamp=window.data_cut_timestamp,
        )
        bundle: ForecastBundle = method.fit_predict(request)
        actual = actual_record.units_sold

        # Build a 1000-sample empirical bag from the quantiles for CRPS
        levels = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
        values = np.array(
            [
                bundle.quantiles.q05, bundle.quantiles.q10, bundle.quantiles.q25,
                bundle.quantiles.q50, bundle.quantiles.q75, bundle.quantiles.q90,
                bundle.quantiles.q95,
            ]
        )
        u = np.random.default_rng(seed).uniform(0.05, 0.95, size=1000)
        samples = np.interp(u, levels, values)

        results.append(
            WindowResult(
                window_index=window.window_index,
                method_id=method.method_id,
                sku_id=request.sku_id,
                location_id=request.location_id,
                bucket=actual_record.bucket,
                actual=actual,
                forecast_mean=bundle.mean,
                smape=smape(actual, bundle.mean),
                crps=crps(actual, samples),
                pinball_q50=pinball_loss(actual, bundle.quantiles.q50, 0.50),
                pinball_q90=pinball_loss(actual, bundle.quantiles.q90, 0.90),
                wis=wis(actual, bundle.quantiles),
            )
        )
    return results


def summarize(results: list[WindowResult]) -> BacktestSummary:
    """Aggregate per-window-per-bucket scores into a method-level summary."""
    if not results:
        raise ValueError("results is empty")
    method_id = results[0].method_id
    if any(r.method_id != method_id for r in results):
        raise ValueError("results contain multiple method_ids; summarize one at a time")

    smapes = [r.smape for r in results if r.smape is not None]
    return BacktestSummary(
        method_id=method_id,
        n_windows=len({r.window_index for r in results}),
        mean_crps=float(np.mean([r.crps for r in results])),
        mean_smape=float(np.mean(smapes)) if smapes else None,
        mean_pinball_q50=float(np.mean([r.pinball_q50 for r in results])),
        mean_pinball_q90=float(np.mean([r.pinball_q90 for r in results])),
        mean_wis=float(np.mean([r.wis for r in results])),
    )


def mark_benchmark_beating(
    candidate: BacktestSummary,
    benchmarks: list[BacktestSummary],
) -> BacktestSummary:
    """Per BACKTESTING.md §6.3: a method must beat ALL mandatory benchmarks
    on CRPS to qualify for production use.
    """
    beats_all = all(candidate.mean_crps < b.mean_crps for b in benchmarks)
    return BacktestSummary(
        method_id=candidate.method_id,
        n_windows=candidate.n_windows,
        mean_crps=candidate.mean_crps,
        mean_smape=candidate.mean_smape,
        mean_pinball_q50=candidate.mean_pinball_q50,
        mean_pinball_q90=candidate.mean_pinball_q90,
        mean_wis=candidate.mean_wis,
        beats_all_benchmarks=beats_all,
    )
