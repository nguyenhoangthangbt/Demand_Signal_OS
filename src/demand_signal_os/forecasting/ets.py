"""ETS forecasting method — Nixtla AutoETS wrapper.

Reference: Hyndman et al. (2008), *Forecasting with Exponential Smoothing*;
Hyndman & Athanasopoulos (2021), *Forecasting: Principles and Practice* (3rd ed.).

Per CONSTITUTION §10: wraps `statsforecast.models.AutoETS`. Produces
probabilistic forecasts via state-space innovation variance — no post-hoc
quantile fitting needed.
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


class ETSMethod:
    """AutoETS state-space wrapper. Implements ForecastMethod protocol.

    Optional ``min_quantile_spread`` enforces a band-width floor on the
    emitted quantiles per the D5 UAT-1b finding (2026-06-08). On
    near-noiseless input, ETS correctly infers zero innovation variance
    and the band collapses to ~3e-9 — statistically right but breaks
    downstream safety_stock / drift detection. When set, the floor is
    applied symmetrically around q50 (q50 preserved exactly). See
    ``forecasting/band_guard.py``.
    """

    method_id: str = "ets"

    def __init__(
        self,
        *,
        season_length: int = 12,
        model: str = "ZZZ",
        min_quantile_spread: float | None = None,
    ):
        self.season_length = season_length
        self.model = model
        self.min_quantile_spread = min_quantile_spread

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        # Import locally so the package imports even if statsforecast isn't
        # installed yet (lets ops_schemas + protocol be used standalone).
        from statsforecast.models import AutoETS

        history = np.asarray(request.history, dtype=float)
        h = len(request.horizon_buckets)
        if h == 0:
            raise ValueError("horizon_buckets is empty")

        model = AutoETS(model=self.model, season_length=self.season_length)
        model = model.fit(history)
        # statsforecast predict returns a dict with 'mean' and intervals when level given
        result = model.predict(h=h, level=[80, 90])

        # Take the first horizon bucket as the per-bundle representation.
        # Multi-bucket bundles are emitted by the caller producing one
        # ForecastBundle per (sku, location, bucket).
        mean_path = np.asarray(result["mean"], dtype=float)
        lo80 = np.asarray(result["lo-80"], dtype=float)
        hi80 = np.asarray(result["hi-80"], dtype=float)
        # 90% intervals available too but unused for now — sigma inferred
        # from the 80% band is sufficient. Re-enable when emitting a
        # second confidence-level family on the bundle.

        # Build a synthetic sample distribution from the parametric intervals
        # so we can emit canonical quantiles. ETS innovations are
        # approximately Gaussian, so we infer sigma from the 80% interval.
        # sigma_80 = (hi80 - lo80) / (2 * 1.2816)  # z(0.9) = 1.2816
        # Use first horizon step for the bundle.
        mu = float(mean_path[0])
        sigma = float((hi80[0] - lo80[0]) / (2 * 1.2816))
        sigma = max(sigma, 1e-9)
        rng = np.random.default_rng(request.seed)
        samples = rng.normal(loc=mu, scale=sigma, size=10_000)
        q = quantiles_from_samples(samples)
        quantiles = Quantiles(**q)

        # Apply minimum band-width guard (D5 UAT-1b — 2026-06-08).
        if self.min_quantile_spread is not None:
            from demand_signal_os.forecasting.band_guard import apply_min_band_floor
            quantiles = apply_min_band_floor(quantiles, self.min_quantile_spread)

        feature_hash = hashlib.sha256(history.tobytes()).hexdigest()[:16]
        provenance = ForecastProvenance(
            forecast_bundle_id=str(uuid.uuid4()),
            model_id=f"ets-{self.model}-s{self.season_length}",
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
            quantiles=quantiles,
            distribution=ProbabilisticDistribution(
                family="normal",
                params={"mean": mu, "std": sigma},
            ),
            mean=mu,
            method=self.method_id,
            provenance=provenance,
        )


_method: ForecastMethod = ETSMethod()  # protocol-conformance check at import
