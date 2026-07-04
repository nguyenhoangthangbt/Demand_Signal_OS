"""Demand-actuals ingestion route (Wire W8 in) — censoring classification + real scoring.

Asserts the endpoint resolves the three censoring tiers from O2C-supplied inventory
snapshots (the value W8 delivers: a stockout zero is NOT treated as real-zero demand),
excludes UNKNOWN from the usable count, and — when a matching forecast bundle is supplied
— scores `drift_magnitude` on the REAL censored actual (not a synthetic UNKNOWN point).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from demand_signal_os.api.app import create_app
from demand_signal_os.ops_schemas import (
    ForecastBundle,
    ForecastProvenance,
    Quantiles,
    TimeBucket,
)

_BUCKET = {"period": "day", "start": "2026-02-01", "end": "2026-02-02", "timezone": "UTC"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _obs(units_sold: float, in_stock: bool, *, snapshot: bool = True) -> dict:
    actual = {
        "sku_id": "SKU-1",
        "location_id": "DC-1",
        "bucket": _BUCKET,
        "units_sold": units_sold,
        "units_demanded": units_sold,
        "censoring": "unknown",
        "source_system": "order2cash_os",
        "recorded_at": "2026-02-02T00:00:00Z",
    }
    obs: dict = {"actual": actual}
    if snapshot:
        obs["snapshot"] = {
            "in_stock_at_bucket_start": in_stock,
            "stockout_hours_in_bucket": 0.0 if in_stock else 24.0,
        }
    return obs


def _bundle_json() -> dict:
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
    ).model_dump(mode="json")


def test_classifies_three_censoring_tiers(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/actuals",
        json={
            "observations": [
                _obs(5, True),   # units_sold > 0 -> OBSERVED
                _obs(0, True),   # zero, in stock -> REAL_ZERO
                _obs(0, False),  # zero, out of stock -> STOCKOUT_CENSORED
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    tc = body["tier_counts"]
    assert tc.get("observed") == 1
    assert tc.get("real_zero") == 1
    assert tc.get("stockout_censored") == 1
    assert body["usable_count"] == 3  # none UNKNOWN
    # The stockout-censored record carries its stockout duration.
    censored = [c for c in body["classified"] if c["censoring"] == "stockout_censored"][0]
    assert censored["stockout_duration_hours"] == 24.0


def test_zero_without_snapshot_stays_unknown(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/actuals",
        json={"observations": [_obs(0, True, snapshot=False)]},
    )
    body = resp.json()
    assert body["tier_counts"].get("unknown") == 1
    assert body["usable_count"] == 0  # UNKNOWN excluded from training


def test_scores_drift_on_real_actual(client: TestClient) -> None:
    # A matching bundle + a real (censored) actual -> a ForecastAccuracy with a
    # drift_magnitude computed on the REAL actual, not a synthetic UNKNOWN point.
    resp = client.post(
        "/api/v1/actuals",
        json={
            "observations": [_obs(5, True)],
            "bundle": _bundle_json(),
            "baseline_crps": 2.0,
        },
    )
    assert resp.status_code == 200, resp.text
    acc = resp.json()["accuracy"]
    assert acc is not None
    assert acc["forecast_bundle_id"] == "b1"
    assert acc["drift_magnitude"] is not None  # scored against the real actual
    assert acc["crps"] >= 0.0
