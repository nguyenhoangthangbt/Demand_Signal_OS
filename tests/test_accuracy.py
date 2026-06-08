"""Tests for the accuracy.evaluate() producer (Phase 3 wire-up)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from demand_signal_os.accuracy import (
    aggregate_drift,
    evaluate,
    is_finite_drift,
)
from demand_signal_os.ops_schemas import (
    CensoringFlag,
    DemandActual,
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
    TimeBucket,
)


def _bucket() -> TimeBucket:
    return TimeBucket(period="day", start=date(2026, 6, 1), end=date(2026, 6, 2))


def _provenance(seed: int = 42, bundle_id: str = "b1") -> ForecastProvenance:
    return ForecastProvenance(
        forecast_bundle_id=bundle_id,
        model_id="ets",
        commit_sha="dev",
        seed=seed,
        feature_set_hash="x",
        data_cut_timestamp=datetime(2026, 6, 1, tzinfo=UTC),
        produced_at=datetime(2026, 6, 1, tzinfo=UTC),
    )


def _bundle(
    *,
    mean: float = 10.0,
    sku: str = "SKU-1",
    location: str = "DC-1",
    seed: int = 42,
    bundle_id: str = "b1",
    horizon_label: str = "operational",
    spread: float = 4.0,
) -> ForecastBundle:
    q = Quantiles(
        q05=mean - spread,
        q10=mean - spread * 0.75,
        q25=mean - spread * 0.4,
        q50=mean,
        q75=mean + spread * 0.4,
        q90=mean + spread * 0.75,
        q95=mean + spread,
    )
    return ForecastBundle(
        sku_id=sku,
        location_id=location,
        bucket=_bucket(),
        horizon_label=horizon_label,  # type: ignore[arg-type]
        quantiles=q,
        mean=mean,
        method="ets",
        provenance=_provenance(seed=seed, bundle_id=bundle_id),
    )


def _actual(
    *,
    units: float = 10.0,
    sku: str = "SKU-1",
    location: str = "DC-1",
) -> DemandActual:
    return DemandActual(
        sku_id=sku,
        location_id=location,
        bucket=_bucket(),
        units_sold=units,
        censoring=CensoringFlag.OBSERVED if units > 0 else CensoringFlag.REAL_ZERO,
        source_system="test",
        recorded_at=datetime(2026, 6, 2, tzinfo=UTC),
    )


# ─────────────────────────────────────────────────────────────────────────────
# evaluate() core behavior
# ─────────────────────────────────────────────────────────────────────────────


def test_evaluate_returns_forecastaccuracy() -> None:
    acc = evaluate(_bundle(), _actual())
    assert acc.forecast_bundle_id == "b1"
    assert acc.sku_id == "SKU-1"
    assert acc.location_id == "DC-1"
    assert acc.forecast_horizon_label == "operational"


def test_evaluate_perfect_forecast_minimizes_crps() -> None:
    """Tight forecast (small spread) on a near-perfect actual produces a
    small CRPS."""
    acc = evaluate(_bundle(mean=10.0, spread=0.5), _actual(units=10.0))
    # With spread=0.5 and actual=10.0, CRPS should be very small
    assert acc.crps < 0.2


def test_evaluate_bad_forecast_inflates_crps() -> None:
    """Forecast centered far from the actual produces large CRPS."""
    tight_on_target = evaluate(_bundle(mean=10.0, spread=0.5), _actual(units=10.0))
    tight_off_target = evaluate(_bundle(mean=10.0, spread=0.5), _actual(units=100.0))
    assert tight_off_target.crps > 10 * tight_on_target.crps


def test_evaluate_smape_zero_when_perfect() -> None:
    acc = evaluate(_bundle(mean=10.0), _actual(units=10.0))
    assert acc.smape == 0.0


def test_evaluate_pinball_at_q50_is_half_abs_error_when_q50_is_mean() -> None:
    acc = evaluate(_bundle(mean=10.0), _actual(units=12.0))
    # q50 == mean == 10.0; actual = 12.0; |diff| = 2.0; pinball@0.5 = 1.0
    assert math.isclose(acc.pinball_q50, 1.0, rel_tol=1e-6)


def test_evaluate_mape_none_when_actual_is_zero() -> None:
    acc = evaluate(_bundle(mean=10.0), _actual(units=0.0))
    assert acc.mape is None


def test_evaluate_horizon_remaining_passthrough() -> None:
    acc = evaluate(_bundle(), _actual(),
                   forecast_horizon_remaining_seconds=3600.0)
    assert acc.forecast_horizon_remaining == 3600.0


# ─────────────────────────────────────────────────────────────────────────────
# Drift magnitude — the load-bearing field for the PlanningOS critic
# ─────────────────────────────────────────────────────────────────────────────


def test_evaluate_no_baseline_means_no_drift_signal() -> None:
    """When baseline_crps is not supplied, drift_magnitude must be None
    (and the critic treats this iter as carrying no drift signal)."""
    acc = evaluate(_bundle(), _actual())
    assert acc.drift_magnitude is None
    assert acc.actuals_drift_flag is False
    assert acc.baseline_crps is None


def test_evaluate_drift_below_threshold_does_not_flag() -> None:
    """current_crps < 1.5x baseline → no drift flag."""
    # Trigger small crps via tight forecast on target
    acc = evaluate(_bundle(mean=10.0, spread=1.0), _actual(units=10.0),
                   baseline_crps=10.0)  # big baseline → ratio << 1.5
    assert acc.drift_magnitude is not None
    assert acc.drift_magnitude < 1.5
    assert acc.actuals_drift_flag is False


def test_evaluate_drift_above_threshold_flags() -> None:
    """current_crps > 1.5x baseline → flag fires."""
    acc = evaluate(_bundle(mean=10.0, spread=1.0), _actual(units=100.0),
                   baseline_crps=10.0)  # bad forecast → big crps / 10
    assert acc.drift_magnitude is not None
    assert acc.drift_magnitude > 1.5
    assert acc.actuals_drift_flag is True


def test_evaluate_drift_zero_baseline_treated_as_no_baseline() -> None:
    """Guard against divide-by-zero: baseline_crps=0 → drift_magnitude=None."""
    acc = evaluate(_bundle(), _actual(), baseline_crps=0.0)
    assert acc.drift_magnitude is None


# ─────────────────────────────────────────────────────────────────────────────
# Identity-mismatch errors
# ─────────────────────────────────────────────────────────────────────────────


def test_evaluate_sku_mismatch_raises() -> None:
    bundle = _bundle(sku="SKU-1")
    actual = _actual(sku="SKU-2")
    with pytest.raises(ValueError, match="sku_id"):
        evaluate(bundle, actual)


def test_evaluate_location_mismatch_raises() -> None:
    bundle = _bundle(location="DC-1")
    actual = _actual(location="DC-2")
    with pytest.raises(ValueError, match="location_id"):
        evaluate(bundle, actual)


def test_evaluate_bucket_mismatch_raises() -> None:
    bundle = _bundle()
    actual = _actual()
    other_bucket = TimeBucket(period="day", start=date(2026, 7, 1),
                              end=date(2026, 7, 2))
    actual = actual.model_copy(update={"bucket": other_bucket})
    with pytest.raises(ValueError, match="bucket"):
        evaluate(bundle, actual)


# ─────────────────────────────────────────────────────────────────────────────
# Determinism + provenance
# ─────────────────────────────────────────────────────────────────────────────


def test_evaluate_is_deterministic() -> None:
    """Same bundle + actual → identical accuracy each call (seeded CRPS)."""
    bundle = _bundle()
    actual = _actual()
    a1 = evaluate(bundle, actual, baseline_crps=5.0)
    a2 = evaluate(bundle, actual, baseline_crps=5.0)
    assert a1 == a2


def test_evaluate_carries_bundle_provenance() -> None:
    acc = evaluate(_bundle(bundle_id="my-bundle-id"), _actual())
    assert acc.forecast_bundle_id == "my-bundle-id"
    assert "my-bundle-id" in acc.actuals_provenance


def test_evaluate_extra_provenance_appended() -> None:
    acc = evaluate(_bundle(), _actual(),
                   actuals_provenance_extra=["o2c-event-1", "o2c-event-2"])
    assert acc.actuals_provenance[0] == "b1"
    assert "o2c-event-1" in acc.actuals_provenance
    assert "o2c-event-2" in acc.actuals_provenance


# ─────────────────────────────────────────────────────────────────────────────
# aggregate_drift + is_finite_drift helpers
# ─────────────────────────────────────────────────────────────────────────────


def test_aggregate_drift_empty_returns_none() -> None:
    assert aggregate_drift([]) is None


def test_aggregate_drift_all_none_returns_none() -> None:
    a = evaluate(_bundle(), _actual())  # no baseline → drift None
    b = evaluate(_bundle(), _actual())
    assert aggregate_drift([a, b]) is None


def test_aggregate_drift_simple_mean() -> None:
    accs = [
        evaluate(_bundle(mean=10.0, spread=1.0), _actual(units=15.0),
                 baseline_crps=2.0),  # drift_magnitude likely ~3
        evaluate(_bundle(mean=10.0, spread=1.0), _actual(units=10.0),
                 baseline_crps=2.0),  # drift_magnitude likely ~0.1
    ]
    agg = aggregate_drift(accs)
    assert agg is not None
    # Mean of the two non-None drift values
    expected = sum(a.drift_magnitude for a in accs) / 2  # type: ignore[misc]
    assert math.isclose(agg, expected, rel_tol=1e-6)


def test_aggregate_drift_weighted_by_horizon() -> None:
    """When weight_by_horizon_remaining=True, longer-horizon bundles
    contribute more — they carry more "urgency"."""
    a = evaluate(_bundle(mean=10.0, spread=1.0), _actual(units=20.0),
                 baseline_crps=2.0,
                 forecast_horizon_remaining_seconds=10.0)
    b = evaluate(_bundle(mean=10.0, spread=1.0), _actual(units=10.0),
                 baseline_crps=2.0,
                 forecast_horizon_remaining_seconds=1000.0)
    simple = aggregate_drift([a, b], weight_by_horizon_remaining=False)
    weighted = aggregate_drift([a, b], weight_by_horizon_remaining=True)
    # b dominates the weighted average → weighted closer to b's drift
    assert simple is not None and weighted is not None
    assert abs(weighted - b.drift_magnitude) < abs(simple - b.drift_magnitude)  # type: ignore[operator]


def test_is_finite_drift_rejects_none_and_nan_and_zero() -> None:
    assert is_finite_drift(1.5) is True
    assert is_finite_drift(None) is False
    assert is_finite_drift(float("nan")) is False
    assert is_finite_drift(0.0) is False
    assert is_finite_drift(-1.0) is False
