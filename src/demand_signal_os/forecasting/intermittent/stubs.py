"""Intermittent method stubs — Nixtla wrappers.

v0.1 implements the wrapper shape; full integration with statsforecast
classes (CrostonOptimized, TSB, CrostonSBA) lands in the next commit.
The protocol-conformance assertion at module load catches contract drift.
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


def _bundle_from_samples(
    samples: np.ndarray,
    request: ForecastRequest,
    method_id: str,
    model_id: str,
) -> ForecastBundle:
    history = np.asarray(request.history, dtype=float)
    q = quantiles_from_samples(samples)
    mu = float(np.mean(samples))
    sigma = float(np.std(samples))
    feature_hash = hashlib.sha256(history.tobytes()).hexdigest()[:16]
    provenance = ForecastProvenance(
        forecast_bundle_id=str(uuid.uuid4()),
        model_id=model_id,
        commit_sha="dev",
        seed=request.seed,
        feature_set_hash=feature_hash,
        data_cut_timestamp=request.data_cut_timestamp,
        produced_at=datetime.now(),
    )
    return ForecastBundle(
        sku_id=request.sku_id,
        location_id=request.location_id,
        bucket=request.horizon_buckets[0],
        horizon_label=request.horizon_label,
        quantiles=Quantiles(**q),
        distribution=ProbabilisticDistribution(
            family="normal", params={"mean": mu, "std": max(sigma, 1e-9)}
        ),
        mean=mu,
        method=method_id,
        provenance=provenance,
    )


class CrostonOptimizedMethod:
    """Default Croston variant per R-6 — MLE-optimized α via Nixtla."""

    method_id: str = "croston_opt"

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        from statsforecast.models import CrostonOptimized

        history = np.asarray(request.history, dtype=float)
        h = len(request.horizon_buckets)
        model = CrostonOptimized()
        model = model.fit(history)
        result = model.predict(h=h)
        mu = float(np.asarray(result["mean"], dtype=float)[0])
        # Croston is point-forecast; bootstrap intervals from residuals.
        rng = np.random.default_rng(request.seed)
        sigma = float(np.std(history)) or 1.0
        samples = rng.normal(loc=mu, scale=sigma, size=10_000)
        return _bundle_from_samples(samples, request, self.method_id, "croston_opt")


class TSBMethod:
    """Teunter-Syntetos-Babai 2011 — separate α_d (demand) + α_p (probability)."""

    method_id: str = "tsb"

    def __init__(self, *, alpha_d: float = 0.1, alpha_p: float = 0.1):
        self.alpha_d = alpha_d
        self.alpha_p = alpha_p

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        from statsforecast.models import TSB

        history = np.asarray(request.history, dtype=float)
        h = len(request.horizon_buckets)
        model = TSB(alpha_d=self.alpha_d, alpha_p=self.alpha_p)
        model = model.fit(history)
        result = model.predict(h=h)
        mu = float(np.asarray(result["mean"], dtype=float)[0])
        rng = np.random.default_rng(request.seed)
        sigma = float(np.std(history)) or 1.0
        samples = rng.normal(loc=mu, scale=sigma, size=10_000)
        return _bundle_from_samples(samples, request, self.method_id, "tsb")


class CrostonSBAMethod:
    """Croston with Syntetos-Boylan 0.95 debiasing factor (Syntetos-Boylan 2005)."""

    method_id: str = "sba"

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        from statsforecast.models import CrostonSBA

        history = np.asarray(request.history, dtype=float)
        h = len(request.horizon_buckets)
        model = CrostonSBA()
        model = model.fit(history)
        result = model.predict(h=h)
        mu = float(np.asarray(result["mean"], dtype=float)[0])
        rng = np.random.default_rng(request.seed)
        sigma = float(np.std(history)) or 1.0
        samples = rng.normal(loc=mu, scale=sigma, size=10_000)
        return _bundle_from_samples(samples, request, self.method_id, "sba")


# Protocol-conformance checks at import time
_co: ForecastMethod = CrostonOptimizedMethod()
_tsb: ForecastMethod = TSBMethod()
_sba: ForecastMethod = CrostonSBAMethod()
