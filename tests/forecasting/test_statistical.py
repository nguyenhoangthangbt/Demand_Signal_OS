"""Tests for the expansion statistical forecasters (arima/theta/ces)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from demand_signal_os.forecasting.protocol import ForecastRequest
from demand_signal_os.forecasting.statistical import (
    AutoARIMAMethod,
    AutoCESMethod,
    AutoThetaMethod,
)
from demand_signal_os.ops_schemas import TimeBucket

_CUT = datetime(2026, 1, 1, tzinfo=UTC)


def _request(seed: int = 42) -> ForecastRequest:
    from datetime import date

    hist = [10 + 3 * ((i % 7) - 3) + (i % 2) for i in range(40)]
    bucket = TimeBucket(
        period="day", start=date(2026, 2, 10), end=date(2026, 2, 11)
    )
    return ForecastRequest(
        sku_id="SKU-1", location_id="DC-1", history=[float(x) for x in hist],
        history_buckets=[], horizon_buckets=[bucket], horizon_label="operational",
        seed=seed, data_cut_timestamp=_CUT,
    )


@pytest.mark.parametrize(
    "method_cls,method_id",
    [(AutoARIMAMethod, "arima"), (AutoThetaMethod, "theta"), (AutoCESMethod, "ces")],
)
def test_produces_valid_monotone_bundle(method_cls: type, method_id: str) -> None:
    bundle = method_cls(season_length=7).fit_predict(_request())
    assert bundle.method == method_id
    q = bundle.quantiles
    # Monotone non-decreasing canonical quantiles.
    vals = [q.q05, q.q10, q.q25, q.q50, q.q75, q.q90, q.q95]
    assert vals == sorted(vals)
    assert q.q05 <= bundle.mean <= q.q95


@pytest.mark.parametrize("method_cls", [AutoARIMAMethod, AutoThetaMethod, AutoCESMethod])
def test_deterministic_same_seed(method_cls: type) -> None:
    a = method_cls(season_length=7).fit_predict(_request(seed=7))
    b = method_cls(season_length=7).fit_predict(_request(seed=7))
    assert a.quantiles.model_dump() == b.quantiles.model_dump()
    assert a.mean == b.mean
