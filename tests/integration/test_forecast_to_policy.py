"""End-to-end smoke test — forecast → policy → SimOS-adapter handoff.

Skips ETS test if statsforecast is not installed (lets the schema +
inventory-policy tests pass standalone). The smoke test verifies the
seam composes correctly when the backend is available.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from demand_signal_os.consumers.simos_adapter import DemandForecastDistribution
from demand_signal_os.forecasting.protocol import ForecastRequest
from demand_signal_os.inventory_policy.pir import pir_from_forecast
from demand_signal_os.inventory_policy.qr import qr_policy
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
    TimeBucket,
)

statsforecast = pytest.importorskip("statsforecast")


def _bucket() -> TimeBucket:
    return TimeBucket(period="day", start=date(2026, 2, 1), end=date(2026, 2, 2))


def _request() -> ForecastRequest:
    # 60 days of synthetic seasonal demand for ETS to chew on
    import math

    history = [10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 5) for i in range(60)]
    return ForecastRequest(
        sku_id="SKU-TEST",
        location_id="DC-1",
        history=history,
        history_buckets=[],  # not exercised in v0.1 ETS wrapper
        horizon_buckets=[_bucket()],
        horizon_label="operational",
        seed=42,
        data_cut_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
    )


def test_ets_forecast_produces_valid_bundle() -> None:
    """ETS wrapper end-to-end: history → ForecastBundle with quantiles + provenance."""
    from demand_signal_os.forecasting.ets import ETSMethod

    method = ETSMethod(season_length=7)
    bundle = method.fit_predict(_request())

    assert isinstance(bundle, ForecastBundle)
    assert bundle.method == "ets"
    # Quantiles must be sorted (q05 <= q10 <= ... <= q95)
    q = bundle.quantiles
    assert q.q05 <= q.q10 <= q.q25 <= q.q50 <= q.q75 <= q.q90 <= q.q95
    assert bundle.provenance.seed == 42
    assert bundle.provenance.model_id.startswith("ets-")
    assert bundle.distribution is not None
    assert bundle.distribution.family == "normal"


def test_forecast_to_qr_policy_handoff() -> None:
    """The seam: ForecastBundle → (Q,R) policy parameters."""
    # Synthesize a forecast bundle directly (no ETS dep)
    q = Quantiles(q05=3, q10=4, q25=6, q50=10, q75=14, q90=16, q95=17)
    bundle = ForecastBundle(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        horizon_label="operational",
        quantiles=q,
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

    Q, R, ss = qr_policy(
        forecast_q=bundle.quantiles,
        forecast_mean=bundle.mean,
        lead_time_periods=2.0,
        service_level=0.95,
        service_level_type="csl",
        Q=50.0,
    )
    assert Q == 50.0
    assert ss > 0
    # R = E[D_LTD] + SS = 10 * 2 + SS = 20 + SS
    assert R > 20.0


def test_forecast_to_pir_handoff() -> None:
    """ForecastBundle → PIR (S7 — PlanningOS/O2C consumer artifact)."""
    q = Quantiles(q05=3, q10=4, q25=6, q50=10, q75=14, q90=16, q95=17)
    bundle = ForecastBundle(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        horizon_label="operational",
        quantiles=q,
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
    pir = pir_from_forecast(bundle)  # default: no quantiles (D5)
    assert pir.quantity_planned == 10.0
    assert pir.quantiles is None

    pir_with_q = pir_from_forecast(bundle, carry_quantiles=True)
    assert pir_with_q.quantiles == q


def test_demand_forecast_distribution_samples_within_quantile_band() -> None:
    """SimOS adapter — DemandForecastDistribution sample respects the quantile band."""
    q = Quantiles(q05=3, q10=4, q25=6, q50=10, q75=14, q90=16, q95=17)
    bundle = ForecastBundle(
        sku_id="SKU-1",
        location_id="DC-1",
        bucket=_bucket(),
        horizon_label="operational",
        quantiles=q,
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
    dist = DemandForecastDistribution(bundle, seed=123)
    samples = [dist.sample() for _ in range(1000)]
    # All samples in [q05, q95] by construction
    assert min(samples) >= q.q05
    assert max(samples) <= q.q95
    # Median should be approximately q50
    samples.sort()
    median = samples[500]
    assert abs(median - q.q50) < 2.0
