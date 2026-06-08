"""Mandatory backtest benchmarks per BACKTESTING.md §3.

Every forecasting method must beat all three benchmarks on the same
windows + metrics. A method that fails to beat them on a SKU is excluded
from production use for that SKU (engine falls back to the best benchmark).

References:
- Naive seasonal: Hyndman & Athanasopoulos (2021) ch. 5.2
- SES: Hyndman, Koehler, Ord, Snyder (2008), state-space view
- Moving Average: standard textbook
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

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


def _provenance(request: ForecastRequest, model_id: str) -> ForecastProvenance:
    h = np.asarray(request.history, dtype=float)
    return ForecastProvenance(
        forecast_bundle_id=str(uuid.uuid4()),
        model_id=model_id,
        commit_sha="dev",
        seed=request.seed,
        feature_set_hash=hashlib.sha256(h.tobytes()).hexdigest()[:16],
        data_cut_timestamp=request.data_cut_timestamp,
        produced_at=datetime.now(),
    )


def _bundle(request: ForecastRequest, mu: float, sigma: float, method_id: str,
            model_id: str) -> ForecastBundle:
    sigma = max(float(sigma), 1e-9)
    rng = np.random.default_rng(request.seed)
    samples = rng.normal(loc=mu, scale=sigma, size=10_000)
    q = quantiles_from_samples(samples)
    return ForecastBundle(
        sku_id=request.sku_id,
        location_id=request.location_id,
        bucket=request.horizon_buckets[0],
        horizon_label=request.horizon_label,
        quantiles=Quantiles(**q),
        distribution=ProbabilisticDistribution(
            family="normal", params={"mean": float(mu), "std": sigma}
        ),
        mean=float(mu),
        method=method_id,
        provenance=_provenance(request, model_id),
    )


class NaiveSeasonalMethod:
    """Forecast = actual[t - season_length]. The seasonal floor.

    Reference: Hyndman & Athanasopoulos (2021) ch. 5.2 — `snaive`.
    """

    method_id: str = "naive_seasonal"

    def __init__(self, *, season_length: int = 7):
        self.season_length = season_length

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        history = np.asarray(request.history, dtype=float)
        if len(history) < self.season_length:
            mu = float(np.mean(history)) if len(history) else 0.0
            sigma = float(np.std(history)) if len(history) > 1 else 1.0
        else:
            mu = float(history[-self.season_length])
            # Empirical residual std from same-season-of-week observations.
            seasonal_slice = history[len(history) % self.season_length::self.season_length]
            sigma = float(np.std(seasonal_slice)) if len(seasonal_slice) > 1 else 1.0
        return _bundle(
            request, mu, sigma, self.method_id, f"naive_seasonal-s{self.season_length}"
        )


class SESMethod:
    """Simple Exponential Smoothing with optional MLE-fit alpha.

    State-space view per Hyndman-Koehler-Ord-Snyder (2008). Forecast =
    last smoothed level; residuals give the innovation std.
    """

    method_id: str = "ses"

    def __init__(self, *, alpha: float | None = None):
        self.alpha = alpha  # if None, fit via grid search

    def _fit_alpha(self, history: np.ndarray) -> float:
        if self.alpha is not None:
            return float(self.alpha)
        best_alpha, best_sse = 0.3, float("inf")
        for a in np.linspace(0.05, 0.95, 19):
            level = float(history[0])
            sse = 0.0
            for x in history[1:]:
                err = float(x) - level
                sse += err * err
                level = a * float(x) + (1.0 - a) * level
            if sse < best_sse:
                best_sse, best_alpha = sse, float(a)
        return best_alpha

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        history = np.asarray(request.history, dtype=float)
        if len(history) == 0:
            raise ValueError("SES requires at least one historical observation")
        alpha = self._fit_alpha(history)
        level = float(history[0])
        residuals: list[float] = []
        for x in history[1:]:
            residuals.append(float(x) - level)
            level = alpha * float(x) + (1.0 - alpha) * level
        sigma = float(np.std(residuals)) if residuals else 1.0
        return _bundle(request, level, sigma, self.method_id, f"ses-a{alpha:.2f}")


class MovingAverageMethod:
    """Moving average — forecast = mean of last N observations.

    Floor for stable-mean series.
    """

    method_id: str = "moving_average"

    def __init__(self, *, window: int = 4):
        if window < 1:
            raise ValueError("window must be >= 1")
        self.window = window

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        history = np.asarray(request.history, dtype=float)
        if len(history) == 0:
            raise ValueError("MovingAverage requires at least one historical observation")
        window = min(self.window, len(history))
        mu = float(np.mean(history[-window:]))
        sigma = float(np.std(history[-window:])) if window > 1 else 1.0
        return _bundle(request, mu, sigma, self.method_id, f"ma-w{self.window}")


# Protocol-conformance checks at import time.
_ns: ForecastMethod = NaiveSeasonalMethod()
_ses: ForecastMethod = SESMethod()
_ma: ForecastMethod = MovingAverageMethod()
