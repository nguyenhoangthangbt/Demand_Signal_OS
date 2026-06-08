"""Tests for the DSO -> SimOS arrivals schedule adapter (Phase B)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from demand_signal_os.consumers.simos_arrivals_adapter import (
    bundle_to_schedule_entry,
    forecast_bundles_to_simos_schedule,
    write_simos_arrivals_yaml,
)
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
    TimeBucket,
)


def _bucket(start: date, days: int = 1) -> TimeBucket:
    return TimeBucket(period="day", start=start, end=start + timedelta(days=days))


def _provenance() -> ForecastProvenance:
    return ForecastProvenance(
        forecast_bundle_id="b", model_id="ets", commit_sha="dev",
        seed=42, feature_set_hash="x",
        data_cut_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        produced_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _bundle(
    *, sku: str = "SKU-A", location: str = "DC-A",
    start: date, mean: float = 24.0,
) -> ForecastBundle:
    """24 units/day mean by default = 1 unit/hour."""
    return ForecastBundle(
        sku_id=sku, location_id=location, bucket=_bucket(start),
        horizon_label="operational",
        quantiles=Quantiles(
            q05=mean - 4, q10=mean - 3, q25=mean - 2,
            q50=mean,
            q75=mean + 2, q90=mean + 3, q95=mean + 4,
        ),
        mean=mean,
        method="ets",
        provenance=_provenance(),
    )


# ─── bundle_to_schedule_entry ─────────────────────────────────────────────


def test_bundle_to_entry_converts_to_rate_per_hour() -> None:
    bundle = _bundle(start=date(2026, 7, 1), mean=24.0)  # 24/day = 1/hour
    entry = bundle_to_schedule_entry(bundle, t_seconds=0.0)
    assert entry["time"] == 0.0
    assert math.isclose(entry["rate_per_hour"], 1.0, rel_tol=1e-9)


def test_bundle_to_entry_includes_noise_when_requested() -> None:
    bundle = _bundle(start=date(2026, 7, 1), mean=24.0)
    entry = bundle_to_schedule_entry(bundle, t_seconds=0.0, noise_from_band=True)
    assert "noise_std" in entry
    # IQR = q75-q25 = 4; noise = (4/1.349) / 24 = ~ 0.124
    assert entry["noise_std"] > 0.0


def test_bundle_to_entry_omits_noise_when_disabled() -> None:
    bundle = _bundle(start=date(2026, 7, 1))
    entry = bundle_to_schedule_entry(bundle, t_seconds=0.0, noise_from_band=False)
    assert "noise_std" not in entry


# ─── forecast_bundles_to_simos_schedule ───────────────────────────────────


def test_schedule_block_has_distribution_schedule() -> None:
    bundles = [_bundle(start=date(2026, 7, 1) + timedelta(days=i)) for i in range(3)]
    block = forecast_bundles_to_simos_schedule(bundles)
    assert block["distribution"] == "schedule"
    assert isinstance(block["schedule"], list)
    assert len(block["schedule"]) == 3


def test_schedule_times_are_sequential_in_seconds() -> None:
    bundles = [_bundle(start=date(2026, 7, 1) + timedelta(days=i)) for i in range(3)]
    block = forecast_bundles_to_simos_schedule(bundles)
    times = [e["time"] for e in block["schedule"]]  # type: ignore[index]
    assert times == [0.0, 86400.0, 172800.0]


def test_schedule_rates_reflect_forecast_means() -> None:
    bundles = [
        _bundle(start=date(2026, 7, 1), mean=24.0),
        _bundle(start=date(2026, 7, 2), mean=48.0),
        _bundle(start=date(2026, 7, 3), mean=12.0),
    ]
    block = forecast_bundles_to_simos_schedule(bundles, noise_from_band=False)
    rates = [e["rate_per_hour"] for e in block["schedule"]]  # type: ignore[index]
    assert math.isclose(rates[0], 1.0)
    assert math.isclose(rates[1], 2.0)
    assert math.isclose(rates[2], 0.5)


def test_schedule_with_cycle_duration() -> None:
    bundles = [_bundle(start=date(2026, 7, 1))]
    block = forecast_bundles_to_simos_schedule(
        bundles, cycle_duration_seconds=86400.0
    )
    assert block["cycle_duration"] == 86400.0


def test_empty_bundles_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        forecast_bundles_to_simos_schedule([])


def test_sku_mismatch_raises() -> None:
    bundles = [
        _bundle(sku="A", start=date(2026, 7, 1)),
        _bundle(sku="B", start=date(2026, 7, 2)),
    ]
    with pytest.raises(ValueError, match="sku_id"):
        forecast_bundles_to_simos_schedule(bundles)


def test_location_mismatch_raises() -> None:
    bundles = [
        _bundle(location="X", start=date(2026, 7, 1)),
        _bundle(location="Y", start=date(2026, 7, 2)),
    ]
    with pytest.raises(ValueError, match="location_id"):
        forecast_bundles_to_simos_schedule(bundles)


def test_non_monotone_buckets_raises() -> None:
    bundles = [
        _bundle(start=date(2026, 7, 2)),
        _bundle(start=date(2026, 7, 1)),  # out of order
    ]
    with pytest.raises(ValueError, match="non-monotone"):
        forecast_bundles_to_simos_schedule(bundles)


# ─── write_simos_arrivals_yaml ────────────────────────────────────────────


def test_write_yaml_round_trips_through_yaml_safe_load(tmp_path: Path) -> None:
    bundles = [_bundle(start=date(2026, 7, 1) + timedelta(days=i)) for i in range(3)]
    out = tmp_path / "arrivals.yaml"
    write_simos_arrivals_yaml(bundles, out, noise_from_band=False)
    data = yaml.safe_load(out.read_text())
    assert "sources" in data
    assert len(data["sources"]) == 1
    source = data["sources"][0]
    assert source["entity"]["type"] == "order"
    assert source["entry_node"] == "order_intake"
    assert source["arrivals"]["distribution"] == "schedule"
    assert len(source["arrivals"]["schedule"]) == 3


def test_write_yaml_entity_and_entry_node_overrides(tmp_path: Path) -> None:
    bundles = [_bundle(start=date(2026, 7, 1))]
    out = tmp_path / "arrivals.yaml"
    write_simos_arrivals_yaml(
        bundles, out, entity_type="customer", entry_node="enter_store",
    )
    data = yaml.safe_load(out.read_text())
    assert data["sources"][0]["entity"]["type"] == "customer"
    assert data["sources"][0]["entry_node"] == "enter_store"


# ─── Phase B.1 robustness guards ──────────────────────────────────────────


def test_negative_mean_clips_to_zero_rate() -> None:
    """Forecast mean < 0 (silly upstream bug) → clip to 0 rate, no crash."""
    bundle = _bundle(start=date(2026, 7, 1), mean=-5.0)
    entry = bundle_to_schedule_entry(bundle, t_seconds=0.0,
                                      noise_from_band=False)
    assert entry["rate_per_hour"] == 0.0


def test_zero_mean_produces_zero_rate_and_zero_noise() -> None:
    bundle = _bundle(start=date(2026, 7, 1), mean=0.0)
    entry = bundle_to_schedule_entry(bundle, t_seconds=0.0, noise_from_band=True)
    assert entry["rate_per_hour"] == 0.0
    # Noise clipped to 0 since rate is 0 (would otherwise allow negatives)
    assert entry["noise_std"] == 0.0


def test_nan_mean_raises_loudly() -> None:
    bundle = _bundle(start=date(2026, 7, 1))
    nan_bundle = bundle.model_copy(update={"mean": math.nan})
    with pytest.raises(ValueError, match="bundle.mean must be finite"):
        bundle_to_schedule_entry(nan_bundle, t_seconds=0.0)


def test_inf_mean_raises_loudly() -> None:
    bundle = _bundle(start=date(2026, 7, 1))
    inf_bundle = bundle.model_copy(update={"mean": math.inf})
    with pytest.raises(ValueError, match="bundle.mean must be finite"):
        bundle_to_schedule_entry(inf_bundle, t_seconds=0.0)


def test_nan_quantile_raises_loudly() -> None:
    bundle = _bundle(start=date(2026, 7, 1))
    nan_q = bundle.quantiles.model_copy(update={"q25": math.nan})
    nan_bundle = bundle.model_copy(update={"quantiles": nan_q})
    with pytest.raises(ValueError, match="bundle.quantiles.q25 must be finite"):
        bundle_to_schedule_entry(nan_bundle, t_seconds=0.0, noise_from_band=True)


def test_negative_t_seconds_raises() -> None:
    bundle = _bundle(start=date(2026, 7, 1))
    with pytest.raises(ValueError, match="t_seconds must be >= 0"):
        bundle_to_schedule_entry(bundle, t_seconds=-1.0)


def test_nan_t_seconds_raises() -> None:
    bundle = _bundle(start=date(2026, 7, 1))
    with pytest.raises(ValueError, match="t_seconds must be finite"):
        bundle_to_schedule_entry(bundle, t_seconds=math.nan)


def test_noise_clipped_so_simos_cannot_draw_negative_rates() -> None:
    """noise_std must be < rate_per_hour / 3 so SimOS Normal-around-rate
    can't draw negative arrival rates within ~3 sigma."""
    # Mean of 24 = rate 1.0/hour. Without clipping noise would scale
    # with IQR. Build a wide IQR to force noise_std large.
    q = Quantiles(q05=0, q10=2, q25=5, q50=24, q75=50, q90=100, q95=200)
    wide_bundle = ForecastBundle(
        sku_id="SKU-A", location_id="DC-A", bucket=_bucket(date(2026, 7, 1)),
        horizon_label="operational",
        quantiles=q, mean=24.0, method="ets",
        provenance=_provenance(),
    )
    entry = bundle_to_schedule_entry(wide_bundle, t_seconds=0.0,
                                      noise_from_band=True)
    rate = entry["rate_per_hour"]  # = 1.0
    noise = entry["noise_std"]
    # Noise capped at rate/3
    assert noise <= rate / 3.0 + 1e-9
