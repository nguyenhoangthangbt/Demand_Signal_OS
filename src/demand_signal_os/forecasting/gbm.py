"""Gradient-boosted quantile forecaster — LightGBM.

Reference: Hyndman & Athanasopoulos (2021) ch. 12; LightGBM quantile
regression (`objective='quantile'`). Trains seven LGBM regressors, one
per canonical quantile (q05, q10, q25, q50, q75, q90, q95).

Features (v0.1 defaults):
- Lag features: t-1, t-2, t-3, t-7
- Rolling mean (window 7)
- Day-of-week one-hot

Per CONSTITUTION §8 library-first rule #2: pure function of (data, config,
seed). No file I/O, no network, no global state.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from demand_signal_os.forecasting.protocol import (
    ForecastMethod,
    ForecastRequest,
)
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
)

CANONICAL_QUANTILES = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)


@dataclass
class GBMConfig:
    lags: tuple[int, ...] = (1, 2, 3, 7)
    rolling_window: int = 7
    n_estimators: int = 200
    learning_rate: float = 0.05
    num_leaves: int = 31
    min_data_in_leaf: int = 5
    season_length: int = 7  # day-of-week features


def _build_features(history: np.ndarray, config: GBMConfig) -> tuple[np.ndarray, np.ndarray]:
    """Build (X, y) training matrix from a 1-D history series.

    Each row's features are lag values + rolling mean + day-of-week one-hot.
    The minimum row index is max(lags + rolling_window).
    """
    n = len(history)
    min_start = max(max(config.lags), config.rolling_window)
    if n <= min_start:
        raise ValueError(
            f"history too short ({n}) for lags {config.lags} + "
            f"rolling {config.rolling_window}"
        )

    rows: list[list[float]] = []
    targets: list[float] = []
    for t in range(min_start, n):
        feats: list[float] = [float(history[t - lag]) for lag in config.lags]
        feats.append(float(np.mean(history[t - config.rolling_window : t])))
        dow = [0.0] * config.season_length
        dow[t % config.season_length] = 1.0
        feats.extend(dow)
        rows.append(feats)
        targets.append(float(history[t]))

    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _build_predict_row(history: np.ndarray, config: GBMConfig) -> np.ndarray:
    """Row for predicting position t = len(history)."""
    t = len(history)
    feats: list[float] = [float(history[t - lag]) for lag in config.lags]
    feats.append(float(np.mean(history[t - config.rolling_window : t])))
    dow = [0.0] * config.season_length
    dow[t % config.season_length] = 1.0
    feats.extend(dow)
    return np.asarray([feats], dtype=float)


class GBMQuantileMethod:
    """LightGBM quantile-regression forecaster.

    Trains seven LGBM models (one per canonical quantile) and emits
    a ForecastBundle whose Quantiles are the per-quantile predictions.
    No parametric distribution attached (Quantiles only).
    """

    method_id: str = "gbm"

    def __init__(
        self,
        config: GBMConfig | None = None,
        *,
        min_quantile_spread: float | None = None,
    ):
        self.config = config or GBMConfig()
        self.min_quantile_spread = min_quantile_spread

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        # Local import keeps lightgbm out of the import path for users
        # who only need schemas / inventory_policy.
        import lightgbm as lgb

        history = np.asarray(request.history, dtype=float)
        X_train, y_train = _build_features(history, self.config)
        X_pred = _build_predict_row(history, self.config)

        preds: dict[float, float] = {}
        for alpha in CANONICAL_QUANTILES:
            model = lgb.LGBMRegressor(
                objective="quantile",
                alpha=alpha,
                n_estimators=self.config.n_estimators,
                learning_rate=self.config.learning_rate,
                num_leaves=self.config.num_leaves,
                min_data_in_leaf=self.config.min_data_in_leaf,
                verbosity=-1,
                random_state=request.seed,
            )
            model.fit(X_train, y_train)
            preds[alpha] = float(model.predict(X_pred)[0])

        # LightGBM quantile training does not guarantee monotone quantiles;
        # enforce monotonicity via isotonic projection (pool-adjacent).
        sorted_alphas = sorted(preds)
        vals = [preds[a] for a in sorted_alphas]
        for i in range(1, len(vals)):
            if vals[i] < vals[i - 1]:
                vals[i] = vals[i - 1]
        preds = dict(zip(sorted_alphas, vals, strict=True))

        q = Quantiles(
            q05=preds[0.05], q10=preds[0.10], q25=preds[0.25], q50=preds[0.50],
            q75=preds[0.75], q90=preds[0.90], q95=preds[0.95],
        )
        if self.min_quantile_spread is not None:
            from demand_signal_os.forecasting.band_guard import apply_min_band_floor
            q = apply_min_band_floor(q, self.min_quantile_spread)
        provenance = ForecastProvenance(
            forecast_bundle_id=str(uuid.uuid4()),
            model_id=f"gbm-lgb-n{self.config.n_estimators}",
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
            quantiles=q,
            mean=preds[0.50],  # median used as point forecast
            method=self.method_id,
            provenance=provenance,
        )


_check: ForecastMethod = GBMQuantileMethod()
