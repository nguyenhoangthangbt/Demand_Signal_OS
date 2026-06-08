"""Synthetic-data generator — addresses brainstormer R1 cold-start blocker.

Generates seeded, configurable demand histories matching the v0.1
discrete-manufacturing-distribution archetype: lumpy + often intermittent,
seasonal, with optional stockout censoring.

Decouples engine validation from O2C readiness — the engine can be
backtested before any real-customer data exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np

from demand_signal_os.estimation.censoring import InventorySnapshot, tier1_heuristic
from demand_signal_os.ops_schemas import CensoringFlag, DemandActual, TimeBucket


@dataclass
class SyntheticConfig:
    """Knobs for the synthetic generator.

    All defaults reproduce the v0.1 archetype profile (discrete-mfg
    distribution, daily buckets, mild weekly seasonality, intermittent).
    """

    n_buckets: int = 120
    bucket_period: str = "day"
    base_level: float = 10.0
    seasonal_amplitude: float = 3.0
    season_length: int = 7
    trend_slope: float = 0.0
    intermittency_rate: float = 0.0  # P(real zero) per bucket
    noise_std: float = 1.5
    censoring_rate: float = 0.0  # P(stockout in any given bucket)
    start_date: date = date(2026, 1, 1)


def _bucket_for(start: date, idx: int, period: str) -> TimeBucket:
    if period == "day":
        d = start + timedelta(days=idx)
        return TimeBucket(period="day", start=d, end=d + timedelta(days=1))
    if period == "week":
        d = start + timedelta(weeks=idx)
        return TimeBucket(period="week", start=d, end=d + timedelta(weeks=1))
    raise ValueError(f"unsupported period: {period}")


def generate(
    sku_id: str,
    location_id: str,
    config: SyntheticConfig,
    *,
    seed: int,
) -> list[DemandActual]:
    """Produce a sequence of DemandActual records honoring the config.

    Returns records already passed through the tier-1 censoring heuristic:
    real zeros are labeled REAL_ZERO; stockouts STOCKOUT_CENSORED.
    """
    rng = np.random.default_rng(seed)
    records: list[DemandActual] = []

    for i in range(config.n_buckets):
        bucket = _bucket_for(config.start_date, i, config.bucket_period)

        # True latent demand (uncensored, untruncated)
        seasonal = config.seasonal_amplitude * np.sin(
            2 * np.pi * i / config.season_length
        )
        trend = config.trend_slope * i
        noise = rng.normal(0.0, config.noise_std)
        true_demand = config.base_level + seasonal + trend + noise

        # Inject intermittency (real-zero periods)
        if rng.uniform() < config.intermittency_rate:
            true_demand = 0.0

        true_demand = max(true_demand, 0.0)

        # Inject censoring (out of stock during the bucket)
        in_stock = rng.uniform() > config.censoring_rate
        observed = true_demand if in_stock else 0.0

        # Build the raw record + the matching snapshot
        record = DemandActual(
            sku_id=sku_id,
            location_id=location_id,
            bucket=bucket,
            units_sold=float(observed),
            units_demanded=float(true_demand) if in_stock else None,
            censoring=CensoringFlag.UNKNOWN,
            source_system="synthetic",
            recorded_at=datetime.combine(bucket.end, datetime.min.time()).replace(
                tzinfo=UTC
            ),
        )
        snapshot = InventorySnapshot(
            sku_id=sku_id,
            location_id=location_id,
            in_stock_at_bucket_start=in_stock,
            stockout_hours_in_bucket=24.0 if not in_stock else 0.0,
        )
        records.append(tier1_heuristic(record, snapshot))

    return records


def history_values(records: list[DemandActual]) -> list[float]:
    """Extract units_sold as a plain list for ForecastRequest.history."""
    return [r.units_sold for r in records]
