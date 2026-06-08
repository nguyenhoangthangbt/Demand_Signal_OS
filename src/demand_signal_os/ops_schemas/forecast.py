"""Forecast + distribution + provenance types per CONTRACTS §1.3, §1.5.

ProbabilisticDistribution.family aligns with SimOS's
distributions/registry.py natively-supported families (S2 + R-1) so
SimOS can sample without adapter code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from demand_signal_os.ops_schemas.fallback import ForecastFallbackStrategy
from demand_signal_os.ops_schemas.hierarchy import TimeBucket


class Quantiles(BaseModel):
    schema_version: int = 1
    q05: float
    q10: float
    q25: float
    q50: float
    q75: float
    q90: float
    q95: float


class ProbabilisticDistribution(BaseModel):
    schema_version: int = 1
    family: Literal[
        "normal",
        "lognormal",
        "exponential",
        "empirical",
        "fixed",
        "uniform",
        "triangular",
    ]
    params: dict
    support: tuple[float, float] | None = None


class ForecastProvenance(BaseModel):
    schema_version: int = 1
    forecast_bundle_id: str
    model_id: str
    commit_sha: str
    seed: int
    feature_set_hash: str
    data_cut_timestamp: datetime
    produced_at: datetime


class ForecastBundle(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    horizon_label: Literal["operational", "tactical", "strategic"]
    quantiles: Quantiles
    distribution: ProbabilisticDistribution | None = None
    mean: float
    method: str
    fallback_applied: ForecastFallbackStrategy | None = None
    provenance: ForecastProvenance
