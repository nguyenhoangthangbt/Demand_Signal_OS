"""Bottom-up reconciliation tests — verifies the §5.2 guarantee.

The guarantee: sum of bottom-level quantiles == aggregate-level quantile.
This is the test that proves CONTRACTS §5.2 holds.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from demand_signal_os.forecasting.reconciliation import reconcile_bottom_up
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
    TimeBucket,
)


def _bundle(sku: str, q05: float, q50: float, q95: float, mean: float) -> ForecastBundle:
    bucket = TimeBucket(period="day", start=date(2026, 1, 1), end=date(2026, 1, 2))
    return ForecastBundle(
        sku_id=sku,
        location_id="DC-1",
        bucket=bucket,
        horizon_label="operational",
        quantiles=Quantiles(
            q05=q05, q10=q05 + 1, q25=q05 + 2, q50=q50, q75=q95 - 2, q90=q95 - 1, q95=q95
        ),
        mean=mean,
        method="ets",
        provenance=ForecastProvenance(
            forecast_bundle_id=f"b-{sku}",
            model_id="ets",
            commit_sha="dev",
            seed=42,
            feature_set_hash="x",
            data_cut_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            produced_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    )


def test_bottom_up_sum_quantiles_holds() -> None:
    """CONTRACTS §5.2 — sum of bottom-level quantiles equals aggregate quantile."""
    bottom = [
        _bundle("SKU-1", q05=2.0, q50=10.0, q95=18.0, mean=10.0),
        _bundle("SKU-2", q05=1.0, q50=5.0, q95=9.0, mean=5.0),
        _bundle("SKU-3", q05=3.0, q50=15.0, q95=27.0, mean=15.0),
    ]
    agg_prov = bottom[0].provenance.model_copy(
        update={"forecast_bundle_id": "agg-bundle", "model_id": "bottom_up"}
    )
    agg = reconcile_bottom_up(
        bottom,
        aggregate_provenance=agg_prov,
        aggregate_sku_id="FAMILY-A",
        aggregate_location_id="DC-1",
    )

    # Every quantile must sum exactly
    assert agg.quantiles.q05 == 2.0 + 1.0 + 3.0
    assert agg.quantiles.q50 == 10.0 + 5.0 + 15.0
    assert agg.quantiles.q95 == 18.0 + 9.0 + 27.0
    assert agg.mean == 10.0 + 5.0 + 15.0
    assert agg.method == "bottom_up"
    assert agg.sku_id == "FAMILY-A"
