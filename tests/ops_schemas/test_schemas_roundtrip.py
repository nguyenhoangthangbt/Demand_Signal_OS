"""Schema round-trip tests — verifies every ops_schemas type serializes
to JSON and deserializes back to the same value.

Anchors the v0.1 contract surface. Any schema change must keep round-trip
passing — that's the cost of breaking the contract.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from demand_signal_os.ops_schemas import (
    ArchetypeTag,
    BaseStockParameters,
    CensoringFlag,
    DemandActual,
    DemandSignal,
    ForecastAccuracy,
    ForecastBundle,
    ForecastFallbackStrategy,
    ForecastProvenance,
    InventoryPolicy,
    Location,
    NewsvendorParameters,
    PIR,
    ProbabilisticDistribution,
    QRParameters,
    Quantiles,
    ReorderTrigger,
    SKU,
    SSParameters,
    TimeBucket,
)


def _bucket() -> TimeBucket:
    return TimeBucket(period="day", start=date(2026, 1, 1), end=date(2026, 1, 2))


def _provenance() -> ForecastProvenance:
    return ForecastProvenance(
        forecast_bundle_id="bundle-1",
        model_id="ets-ZZZ-s12",
        commit_sha="abc123",
        seed=42,
        feature_set_hash="deadbeef",
        data_cut_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        produced_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def _quantiles() -> Quantiles:
    return Quantiles(q05=1.0, q10=2.0, q25=5.0, q50=10.0, q75=15.0, q90=18.0, q95=19.0)


def test_sku_roundtrip() -> None:
    sku = SKU(sku_id="SKU-1", abc_class="A", archetype="discrete_mfg")
    assert SKU.model_validate_json(sku.model_dump_json()) == sku


def test_location_roundtrip() -> None:
    loc = Location(location_id="DC-1", location_type="central_dc", region_id="NA")
    assert Location.model_validate_json(loc.model_dump_json()) == loc


def test_demand_actual_roundtrip_all_censoring_flags() -> None:
    for flag in CensoringFlag:
        actual = DemandActual(
            sku_id="SKU-1",
            location_id="DC-1",
            bucket=_bucket(),
            units_sold=0.0 if flag != CensoringFlag.UNKNOWN else 5.0,
            censoring=flag,
            source_system="o2c",
            recorded_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        assert DemandActual.model_validate_json(actual.model_dump_json()) == actual


def test_forecast_bundle_with_distribution_roundtrip() -> None:
    bundle = ForecastBundle(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        horizon_label="operational",
        quantiles=_quantiles(),
        distribution=ProbabilisticDistribution(
            family="normal", params={"mean": 10.0, "std": 3.0}
        ),
        mean=10.0,
        method="ets",
        provenance=_provenance(),
    )
    restored = ForecastBundle.model_validate_json(bundle.model_dump_json())
    assert restored == bundle


def test_forecast_bundle_with_fallback_roundtrip() -> None:
    bundle = ForecastBundle(
        sku_id="SKU-NEW",
        location_id="DC-1",
        bucket=_bucket(),
        horizon_label="operational",
        quantiles=_quantiles(),
        mean=10.0,
        method="fallback",
        fallback_applied=ForecastFallbackStrategy(
            strategy_type="cold_start", fallback="family_aggregate_prior"
        ),
        provenance=_provenance(),
    )
    restored = ForecastBundle.model_validate_json(bundle.model_dump_json())
    assert restored == bundle
    assert restored.fallback_applied is not None
    assert restored.fallback_applied.strategy_type == "cold_start"


@pytest.mark.parametrize(
    "params",
    [
        QRParameters(Q=100.0, R=50.0),
        SSParameters(s=30.0, S=120.0, echelon_index=1),
        BaseStockParameters(base_level=80.0),
        NewsvendorParameters(optimal_quantity=75.0, critical_ratio=0.85),
    ],
)
def test_inventory_policy_discriminated_union(params) -> None:  # type: ignore[no-untyped-def]
    """Discriminated union per policy_type (S8) — every variant round-trips."""
    policy = InventoryPolicy(
        sku_id="SKU-1",
        location_id="DC-1",
        parameters=params,
        safety_stock=20.0,
        service_level_target=0.95,
        service_level_type="csl",
        reorder_triggers=[
            ReorderTrigger(
                trigger_type="below_reorder_point",
                sku_id="SKU-1",
                location_id="DC-1",
                threshold=50.0,
            )
        ],
        forecast_provenance=_provenance(),
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    restored = InventoryPolicy.model_validate_json(policy.model_dump_json())
    assert restored == policy
    assert restored.parameters.policy_type == params.policy_type  # type: ignore[union-attr]


def test_inventory_policy_fill_rate_mode() -> None:
    """U3 — service_level_type can be fill_rate."""
    policy = InventoryPolicy(
        sku_id="SKU-1",
        location_id="DC-1",
        parameters=QRParameters(Q=100.0, R=50.0),
        safety_stock=20.0,
        service_level_target=0.98,
        service_level_type="fill_rate",
        reorder_triggers=[],
        forecast_provenance=_provenance(),
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        valid_until=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    assert policy.service_level_type == "fill_rate"


def test_pir_quantiles_optional() -> None:
    """D5/S7 — PIR.quantiles is optional (ERP consumers expect deterministic)."""
    pir_no_q = PIR(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        quantity_planned=100.0,
        forecast_provenance=_provenance(),
    )
    assert pir_no_q.quantiles is None

    pir_with_q = PIR(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        quantity_planned=100.0,
        quantiles=_quantiles(),
        forecast_provenance=_provenance(),
    )
    assert pir_with_q.quantiles is not None
    # Round-trip both
    assert PIR.model_validate_json(pir_no_q.model_dump_json()) == pir_no_q
    assert PIR.model_validate_json(pir_with_q.model_dump_json()) == pir_with_q


def test_forecast_accuracy_full_fields() -> None:
    """S5 + R-2 — all new fields present."""
    acc = ForecastAccuracy(
        forecast_bundle_id="bundle-1",
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        forecast_horizon_label="operational",
        mape=None,
        smape=0.15,
        crps=2.5,
        pinball_q50=1.8,
        pinball_q90=3.2,
        actuals_drift_flag=False,
        drift_magnitude=1.05,
        baseline_crps=2.3,
        forecast_horizon_remaining=86400.0,
        actuals_provenance=["o2c-event-1", "o2c-event-2"],
    )
    restored = ForecastAccuracy.model_validate_json(acc.model_dump_json())
    assert restored == acc


def test_probabilistic_distribution_all_7_families() -> None:
    """S2 + R-1 — verify all 7 SimOS-aligned families are valid."""
    for family in ("normal", "lognormal", "exponential", "empirical",
                   "fixed", "uniform", "triangular"):
        dist = ProbabilisticDistribution(family=family, params={"k": 1.0})  # type: ignore[arg-type]
        assert ProbabilisticDistribution.model_validate_json(dist.model_dump_json()) == dist
