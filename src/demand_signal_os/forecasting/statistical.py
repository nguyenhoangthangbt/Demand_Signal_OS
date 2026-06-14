"""Additional statistical forecasters — Nixtla statsforecast wrappers.

Panel expansion (2026-06-14): AutoARIMA, AutoTheta, AutoCES. Each is a
Box-Jenkins / M-competition-grade method that, like AutoETS, emits parametric
prediction intervals (``level=``). We reuse the ETS sampling approach: infer a
Gaussian sigma from the 80% interval, sample with the seeded RNG, and emit the
seven canonical quantiles. References:
- ARIMA: Hyndman & Athanasopoulos (2021) ch. 9; Hyndman-Khandakar auto.arima.
- Theta: Assimakopoulos & Nikolopoulos (2000); M3 winner.
- CES: Complex Exponential Smoothing, Svetunkov & Kourentzes (2018).

Per CONSTITUTION §10 (wrap Nixtla) + §9 (seeded reproducibility).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, Protocol

import numpy as np

from demand_signal_os.forecasting.protocol import (
    ForecastMethod,
    ForecastRequest,
    quantiles_from_samples,
)
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    ProbabilisticDistribution,
    Quantiles,
)

_Z90 = 1.2816  # z(0.90); the 80% interval is mu +/- z90 * sigma


class _LevelModel(Protocol):
    def fit(self, y: np.ndarray) -> Any: ...
    def predict(self, h: int, level: list[int]) -> dict[str, Any]: ...


def _bundle_from_level_model(
    model: _LevelModel,
    request: ForecastRequest,
    method_id: str,
    model_id: str,
    *,
    min_quantile_spread: float | None,
) -> ForecastBundle:
    """Fit a statsforecast level-interval model and emit a ForecastBundle.

    Mirrors ETSMethod: sigma inferred from the 80% band, Gaussian sampling
    with the seeded RNG, canonical quantiles (+ optional band-width floor).
    """
    history = np.asarray(request.history, dtype=float)
    h = len(request.horizon_buckets)
    if h == 0:
        raise ValueError("horizon_buckets is empty")

    fitted = model.fit(history)
    result = fitted.predict(h=h, level=[80, 90])

    mu = float(np.asarray(result["mean"], dtype=float)[0])
    lo80 = float(np.asarray(result["lo-80"], dtype=float)[0])
    hi80 = float(np.asarray(result["hi-80"], dtype=float)[0])
    sigma = max((hi80 - lo80) / (2 * _Z90), 1e-9)

    rng = np.random.default_rng(request.seed)
    samples = rng.normal(loc=mu, scale=sigma, size=10_000)
    quantiles = Quantiles(**quantiles_from_samples(samples))
    if min_quantile_spread is not None:
        from demand_signal_os.forecasting.band_guard import apply_min_band_floor
        quantiles = apply_min_band_floor(quantiles, min_quantile_spread)

    provenance = ForecastProvenance(
        forecast_bundle_id=str(uuid.uuid4()),
        model_id=model_id,
        commit_sha="dev",
        seed=request.seed,
        feature_set_hash=hashlib.sha256(history.tobytes()).hexdigest()[:16],
        data_cut_timestamp=request.data_cut_timestamp,
        produced_at=datetime.now(),
    )
    return ForecastBundle(
        sku_id=request.sku_id,
        location_id=request.location_id,
        bucket=request.horizon_buckets[0],
        horizon_label=request.horizon_label,
        quantiles=quantiles,
        distribution=ProbabilisticDistribution(
            family="normal", params={"mean": mu, "std": sigma}
        ),
        mean=mu,
        method=method_id,
        provenance=provenance,
    )


class AutoARIMAMethod:
    """Hyndman-Khandakar auto.arima (statsforecast.AutoARIMA)."""

    method_id: str = "arima"

    def __init__(self, *, season_length: int = 12, min_quantile_spread: float | None = None):
        self.season_length = season_length
        self.min_quantile_spread = min_quantile_spread

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        from statsforecast.models import AutoARIMA

        return _bundle_from_level_model(
            AutoARIMA(season_length=self.season_length), request, self.method_id,
            f"arima-s{self.season_length}", min_quantile_spread=self.min_quantile_spread,
        )


class AutoThetaMethod:
    """Theta method (statsforecast.AutoTheta) — M3 winner."""

    method_id: str = "theta"

    def __init__(self, *, season_length: int = 12, min_quantile_spread: float | None = None):
        self.season_length = season_length
        self.min_quantile_spread = min_quantile_spread

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        from statsforecast.models import AutoTheta

        return _bundle_from_level_model(
            AutoTheta(season_length=self.season_length), request, self.method_id,
            f"theta-s{self.season_length}", min_quantile_spread=self.min_quantile_spread,
        )


class AutoCESMethod:
    """Complex Exponential Smoothing (statsforecast.AutoCES)."""

    method_id: str = "ces"

    def __init__(self, *, season_length: int = 12, min_quantile_spread: float | None = None):
        self.season_length = season_length
        self.min_quantile_spread = min_quantile_spread

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        from statsforecast.models import AutoCES

        return _bundle_from_level_model(
            AutoCES(season_length=self.season_length), request, self.method_id,
            f"ces-s{self.season_length}", min_quantile_spread=self.min_quantile_spread,
        )


# Protocol-conformance checks at import time.
_arima: ForecastMethod = AutoARIMAMethod()
_theta: ForecastMethod = AutoThetaMethod()
_ces: ForecastMethod = AutoCESMethod()
