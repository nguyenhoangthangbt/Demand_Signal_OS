"""GBM (LightGBM quantile) forecaster tests."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from demand_signal_os.forecasting.protocol import ForecastRequest
from demand_signal_os.ops_schemas import ForecastBundle, TimeBucket

lgb = pytest.importorskip("lightgbm")


def _request(history: list[float]) -> ForecastRequest:
    return ForecastRequest(
        sku_id="SKU-1",
        location_id="DC-1",
        history=history,
        history_buckets=[],
        horizon_buckets=[
            TimeBucket(period="day", start=date(2026, 2, 1), end=date(2026, 2, 2))
        ],
        horizon_label="operational",
        seed=42,
        data_cut_timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )


def test_gbm_produces_valid_bundle() -> None:
    from demand_signal_os.forecasting.gbm import GBMQuantileMethod

    # 60 days of synthetic seasonal data
    import math
    history = [10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 5) for i in range(60)]
    method = GBMQuantileMethod()
    bundle = method.fit_predict(_request(history))
    assert isinstance(bundle, ForecastBundle)
    assert bundle.method == "gbm"


def test_gbm_quantiles_are_monotone() -> None:
    """Per the isotonic projection in gbm.py — quantiles must be sorted."""
    from demand_signal_os.forecasting.gbm import GBMQuantileMethod

    import math
    history = [10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 3) for i in range(60)]
    bundle = GBMQuantileMethod().fit_predict(_request(history))
    q = bundle.quantiles
    assert q.q05 <= q.q10 <= q.q25 <= q.q50 <= q.q75 <= q.q90 <= q.q95


def test_gbm_short_history_raises() -> None:
    from demand_signal_os.forecasting.gbm import GBMConfig, GBMQuantileMethod

    config = GBMConfig(lags=(1, 2, 3, 7), rolling_window=7)
    method = GBMQuantileMethod(config=config)
    # min_start = max(7, 7) = 7; history of 8 has only 1 training row → still
    # fails LGBM's min_data_in_leaf=5.
    with pytest.raises(Exception):
        method.fit_predict(_request([1.0, 2.0, 3.0]))


def test_gbm_provenance_carries_seed() -> None:
    from demand_signal_os.forecasting.gbm import GBMQuantileMethod

    import math
    history = [10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 5) for i in range(60)]
    bundle = GBMQuantileMethod().fit_predict(_request(history))
    assert bundle.provenance.seed == 42
    assert bundle.provenance.model_id.startswith("gbm-lgb")
