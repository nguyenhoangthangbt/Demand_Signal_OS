"""o2c_adapter — InventoryPolicy + PIR envelope assembly (Wire W4 producer side).

Asserts the adapter wraps the sovereign policy kernels into a typed InventoryPolicy
with the right discriminated parameters, a below-reorder-point trigger, chained
provenance, and a bucket-derived validity window. Includes the deterministic baseline
(RULE 5): the same bundle + config yields a byte-identical policy, with hardcoded
expected (Q, R, safety_stock) values so any drift in the math surfaces as a test failure.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from demand_signal_os.consumers.o2c_adapter import build_inventory_policy, build_pir
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
    TimeBucket,
)


def _bundle() -> ForecastBundle:
    return ForecastBundle(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=TimeBucket(period="day", start=date(2026, 2, 1), end=date(2026, 2, 2)),
        horizon_label="operational",
        quantiles=Quantiles(q05=3, q10=4, q25=6, q50=10, q75=14, q90=16, q95=17),
        mean=10.0,
        method="ets",
        provenance=ForecastProvenance(
            forecast_bundle_id="b1",
            model_id="ets",
            commit_sha="dev",
            seed=42,
            feature_set_hash="x",
            data_cut_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
            produced_at=datetime(2026, 2, 2, tzinfo=UTC),
        ),
    )


def test_qr_policy_deterministic_baseline() -> None:
    # RULE 5: same inputs -> byte-identical policy, with hardcoded expected values.
    bundle = _bundle()
    p1 = build_inventory_policy(bundle, lead_time_periods=2.0, service_level=0.95)
    p2 = build_inventory_policy(bundle, lead_time_periods=2.0, service_level=0.95)
    assert p1.model_dump(mode="json") == p2.model_dump(mode="json")

    assert p1.parameters.policy_type == "qr"
    # Default Q = mean * lead_time = 10 * 2 = 20 (exact).
    assert p1.parameters.Q == pytest.approx(20.0)
    # sigma_ltd = (q90-q10)/2.5632 * sqrt(2); SS = z_0.95 * sigma_ltd.
    assert p1.safety_stock == pytest.approx(10.8903, rel=1e-3)
    # R = E[D_LTD] + SS = 10*2 + SS.
    assert p1.parameters.R == pytest.approx(20.0 + p1.safety_stock)
    assert p1.parameters.R == pytest.approx(30.8903, rel=1e-3)


def test_qr_trigger_and_provenance() -> None:
    bundle = _bundle()
    policy = build_inventory_policy(bundle, lead_time_periods=2.0)
    assert len(policy.reorder_triggers) == 1
    trig = policy.reorder_triggers[0]
    assert trig.trigger_type == "below_reorder_point"
    assert trig.sku_id == "SKU-1" and trig.location_id == "DC-1"
    assert trig.threshold == pytest.approx(policy.parameters.R)
    # Provenance chains back to the bundle that produced the policy.
    assert policy.forecast_provenance.forecast_bundle_id == "b1"
    # Validity window derives from the bucket (deterministic), not the wall clock.
    assert policy.valid_from == datetime(2026, 2, 1, tzinfo=UTC)
    assert policy.valid_until == datetime(2026, 2, 2, tzinfo=UTC)


def test_order_quantity_override() -> None:
    bundle = _bundle()
    policy = build_inventory_policy(bundle, lead_time_periods=2.0, order_quantity=50.0)
    assert policy.parameters.Q == pytest.approx(50.0)


def test_ss_policy_shape() -> None:
    bundle = _bundle()
    policy = build_inventory_policy(
        bundle,
        lead_time_periods=2.0,
        review_period_periods=1.0,
        policy_type="ss",
        service_level=0.95,
    )
    assert policy.parameters.policy_type == "ss"
    assert policy.safety_stock > 0
    # S = s + mean * review_period.
    assert policy.parameters.S == pytest.approx(policy.parameters.s + bundle.mean * 1.0)
    assert policy.reorder_triggers[0].threshold == pytest.approx(policy.parameters.s)


def test_non_positive_lead_time_raises() -> None:
    with pytest.raises(ValueError, match="lead_time_periods must be positive"):
        build_inventory_policy(_bundle(), lead_time_periods=0.0)


def test_build_pir_defaults_to_q50() -> None:
    bundle = _bundle()
    pir = build_pir(bundle)
    assert pir.quantity_planned == 10.0  # q50
    assert pir.quantiles is None
    assert build_pir(bundle, carry_quantiles=True).quantiles == bundle.quantiles
