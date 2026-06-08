"""Tests for the minimum-band-width guard (Phase A — D5 UAT-1b fix)."""

from __future__ import annotations

import math

import pytest

from demand_signal_os.forecasting.band_guard import apply_min_band_floor
from demand_signal_os.ops_schemas import Quantiles


def _gaussian_q(median: float, sigma: float) -> Quantiles:
    """Build a standard Gaussian-shaped band around `median` with given sigma."""
    return Quantiles(
        q05=median - 1.6449 * sigma,
        q10=median - 1.2816 * sigma,
        q25=median - 0.6745 * sigma,
        q50=median,
        q75=median + 0.6745 * sigma,
        q90=median + 1.2816 * sigma,
        q95=median + 1.6449 * sigma,
    )


def test_guard_disabled_when_min_spread_is_zero() -> None:
    q = _gaussian_q(50.0, 3.0)
    out = apply_min_band_floor(q, 0.0)
    assert out == q


def test_guard_disabled_when_min_spread_is_negative() -> None:
    q = _gaussian_q(50.0, 3.0)
    out = apply_min_band_floor(q, -1.0)
    assert out == q


def test_guard_passes_through_when_band_already_wide() -> None:
    """If current spread >= min_spread, no change."""
    q = _gaussian_q(50.0, 3.0)
    # Spread is about 9.87 — set floor below that
    out = apply_min_band_floor(q, 5.0)
    assert out == q


def test_guard_expands_narrow_band_to_floor() -> None:
    """Spread below floor → expanded to exactly the floor."""
    q = _gaussian_q(50.0, 0.1)  # spread ~ 0.329
    out = apply_min_band_floor(q, 10.0)
    spread = out.q95 - out.q05
    assert math.isclose(spread, 10.0, rel_tol=1e-9)


def test_guard_preserves_q50_exactly() -> None:
    q = _gaussian_q(50.0, 0.001)
    out = apply_min_band_floor(q, 10.0)
    assert out.q50 == 50.0


def test_guard_preserves_monotonicity() -> None:
    q = _gaussian_q(50.0, 0.001)
    out = apply_min_band_floor(q, 10.0)
    assert out.q05 <= out.q10 <= out.q25 <= out.q50 <= out.q75 <= out.q90 <= out.q95


def test_guard_preserves_band_shape_under_scaling() -> None:
    """Skewed band → expanded band keeps the same shape (proportional)."""
    # Skewed band: tail wider on the upper side
    q = Quantiles(
        q05=10.0, q10=12.0, q25=15.0, q50=20.0,
        q75=27.0, q90=33.0, q95=38.0,
    )
    # Current spread 28; force floor to 56 (double)
    out = apply_min_band_floor(q, 56.0)
    # Each quantile distance from q50 should be doubled
    assert math.isclose(out.q50, 20.0, rel_tol=1e-9)
    assert math.isclose(out.q05 - out.q50, 2.0 * (q.q05 - q.q50), rel_tol=1e-9)
    assert math.isclose(out.q95 - out.q50, 2.0 * (q.q95 - q.q50), rel_tol=1e-9)


def test_guard_handles_fully_degenerate_band() -> None:
    """All quantiles equal → expand symmetrically around q50."""
    q = Quantiles(
        q05=42.0, q10=42.0, q25=42.0, q50=42.0,
        q75=42.0, q90=42.0, q95=42.0,
    )
    out = apply_min_band_floor(q, 10.0)
    # q50 preserved
    assert out.q50 == 42.0
    # Spread exactly hits the floor
    assert math.isclose(out.q95 - out.q05, 10.0, rel_tol=1e-9)
    # Monotonicity restored
    assert out.q05 < out.q50 < out.q95
    # Symmetric around q50
    assert math.isclose(out.q95 - out.q50, out.q50 - out.q05, rel_tol=1e-9)


def test_guard_handles_inverted_band() -> None:
    """Pathological inverted band (q05 > q95) → treat as degenerate."""
    q = Quantiles(
        q05=10.0, q10=9.0, q25=8.0, q50=7.0,
        q75=6.0, q90=5.0, q95=4.0,
    )
    out = apply_min_band_floor(q, 10.0)
    # q50 still preserved
    assert out.q50 == 7.0
    # Output now well-ordered
    assert out.q05 < out.q50 < out.q95


# ─── Integration with forecasting methods ─────────────────────────────────


def test_ets_method_with_min_spread_avoids_noiseless_collapse() -> None:
    """The original UAT-1b failure: noiseless ETS input → band collapses
    to ~3e-9. With guard, band expands to the floor."""
    import math as m
    from datetime import UTC, date, datetime

    from demand_signal_os.forecasting.ets import ETSMethod
    from demand_signal_os.forecasting.protocol import ForecastRequest
    from demand_signal_os.ops_schemas import TimeBucket

    history = [50 + 10 * m.sin(2 * m.pi * i / 7) for i in range(100)]
    request = ForecastRequest(
        sku_id="SKU-1", location_id="DC-1",
        history=history, history_buckets=[],
        horizon_buckets=[TimeBucket(
            period="day", start=date(2026, 6, 1), end=date(2026, 6, 2)
        )],
        horizon_label="operational",
        seed=42,
        data_cut_timestamp=datetime.now(UTC),
    )

    # Without guard: band collapses
    unguarded = ETSMethod(season_length=7).fit_predict(request)
    spread_unguarded = unguarded.quantiles.q95 - unguarded.quantiles.q05
    assert spread_unguarded < 1.0, \
        f"control test broken: expected collapse, got spread={spread_unguarded}"

    # With guard at 5.0: spread floors at 5.0
    guarded = ETSMethod(season_length=7,
                       min_quantile_spread=5.0).fit_predict(request)
    spread_guarded = guarded.quantiles.q95 - guarded.quantiles.q05
    assert spread_guarded >= 5.0 - 1e-9, f"guard floor not enforced: {spread_guarded}"


@pytest.mark.parametrize("method_factory", [
    lambda: __import__(
        "demand_signal_os.forecasting.intermittent.stubs", fromlist=["CrostonOptimizedMethod"]
    ).CrostonOptimizedMethod(min_quantile_spread=5.0),
    lambda: __import__(
        "demand_signal_os.forecasting.intermittent.stubs", fromlist=["TSBMethod"]
    ).TSBMethod(min_quantile_spread=5.0),
    lambda: __import__(
        "demand_signal_os.forecasting.intermittent.stubs", fromlist=["CrostonSBAMethod"]
    ).CrostonSBAMethod(min_quantile_spread=5.0),
])
def test_intermittent_methods_honor_guard(method_factory) -> None:  # type: ignore[no-untyped-def]
    """All three intermittent methods accept min_quantile_spread and enforce
    the floor on emitted forecasts."""
    from datetime import UTC, date, datetime

    from demand_signal_os.forecasting.protocol import ForecastRequest
    from demand_signal_os.ops_schemas import TimeBucket

    # Constant series → samples will have tiny std
    history = [10.0] * 100
    request = ForecastRequest(
        sku_id="SKU-1", location_id="DC-1",
        history=history, history_buckets=[],
        horizon_buckets=[TimeBucket(
            period="day", start=date(2026, 6, 1), end=date(2026, 6, 2)
        )],
        horizon_label="operational",
        seed=42,
        data_cut_timestamp=datetime.now(UTC),
    )
    method = method_factory()
    bundle = method.fit_predict(request)
    spread = bundle.quantiles.q95 - bundle.quantiles.q05
    assert spread >= 5.0 - 1e-9, \
        f"{method.method_id} band-guard floor not enforced: spread={spread}"
