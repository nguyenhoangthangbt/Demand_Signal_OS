"""Benchmark method tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from demand_signal_os.backtest.benchmarks import (
    MovingAverageMethod,
    NaiveSeasonalMethod,
    SESMethod,
)
from demand_signal_os.forecasting.protocol import ForecastRequest
from demand_signal_os.ops_schemas import ForecastBundle, TimeBucket


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
        data_cut_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
    )


def test_naive_seasonal_returns_same_position_in_prior_season() -> None:
    """Naive seasonal at h=1: forecast = history[-season_length].

    4 weeks of weekly data [10,20,30,40,50,60,70] * 4. History length 28.
    For the next bucket (position 28), the same position in the prior
    season is history[28 - 7] = history[21] = 10.
    """
    history = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0] * 4
    method = NaiveSeasonalMethod(season_length=7)
    bundle = method.fit_predict(_request(history))
    assert bundle.method == "naive_seasonal"
    assert bundle.mean == 10.0  # history[-7] = position 21 = 10


def test_naive_seasonal_quantiles_are_sorted() -> None:
    history = [10, 20, 30, 40, 50, 60, 70] * 4
    bundle = NaiveSeasonalMethod(season_length=7).fit_predict(_request(history))
    q = bundle.quantiles
    assert q.q05 <= q.q10 <= q.q25 <= q.q50 <= q.q75 <= q.q90 <= q.q95


def test_naive_seasonal_handles_short_history() -> None:
    """Less than one season — degrades to history mean, doesn't crash."""
    bundle = NaiveSeasonalMethod(season_length=7).fit_predict(_request([5, 10, 15]))
    assert isinstance(bundle, ForecastBundle)


def test_ses_fits_alpha_when_none() -> None:
    history = [10.0] * 30
    method = SESMethod(alpha=None)
    bundle = method.fit_predict(_request(history))
    # On a constant series, SES → 10 regardless of alpha
    assert abs(bundle.mean - 10.0) < 0.1


def test_ses_with_fixed_alpha() -> None:
    history = [1.0, 2.0, 3.0, 4.0, 5.0]
    method = SESMethod(alpha=0.5)
    bundle = method.fit_predict(_request(history))
    # SES with alpha=0.5 on 1..5: level converges toward recent obs
    assert 3.0 < bundle.mean < 5.0


def test_ses_empty_history_raises() -> None:
    with pytest.raises(ValueError):
        SESMethod().fit_predict(_request([]))


def test_moving_average_window_4() -> None:
    history = [10.0, 20.0, 30.0, 40.0]
    method = MovingAverageMethod(window=4)
    bundle = method.fit_predict(_request(history))
    assert bundle.mean == 25.0  # (10+20+30+40)/4


def test_moving_average_clamps_window_to_history_length() -> None:
    history = [10.0, 20.0]  # shorter than window=4
    bundle = MovingAverageMethod(window=4).fit_predict(_request(history))
    assert bundle.mean == 15.0  # (10+20)/2 — clamped


def test_moving_average_invalid_window() -> None:
    with pytest.raises(ValueError):
        MovingAverageMethod(window=0)


def test_all_benchmarks_emit_normal_distribution_for_simos() -> None:
    history = [10.0] * 30
    for method in [
        NaiveSeasonalMethod(season_length=7),
        SESMethod(alpha=0.3),
        MovingAverageMethod(window=4),
    ]:
        bundle = method.fit_predict(_request(history))
        assert bundle.distribution is not None
        assert bundle.distribution.family == "normal"
