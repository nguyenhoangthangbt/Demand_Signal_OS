"""ForecastAccuracy type per CONTRACTS §3.4.

Added fields per S5 + R-2:
- drift_magnitude — crps_degradation_ratio = current_crps / baseline_crps
- baseline_crps — reference from walk-forward backtest
- forecast_horizon_remaining — seconds remaining at scoring time
- forecast_horizon_label — lets critic apply different drift thresholds per horizon

WIS is NOT in this schema for v0.1 (per R-3). Implemented as custom
backtest metric in backtest/metrics.py; schema inclusion deferred to v0.2.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from demand_signal_os.ops_schemas.hierarchy import TimeBucket


class ForecastAccuracy(BaseModel):
    schema_version: int = 1
    forecast_bundle_id: str
    sku_id: str
    location_id: str
    bucket: TimeBucket
    forecast_horizon_label: Literal["operational", "tactical", "strategic"]
    mape: float | None  # undefined for intermittent series
    smape: float
    crps: float
    pinball_q50: float
    pinball_q90: float
    actuals_drift_flag: bool
    drift_magnitude: float | None = None
    baseline_crps: float | None = None
    forecast_horizon_remaining: float  # seconds
    actuals_provenance: list[str]
