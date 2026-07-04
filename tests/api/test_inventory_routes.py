"""Inventory-policy route (Wire W4 out) — DSO exposes typed InventoryPolicy + PIR.

Asserts the endpoint returns a typed policy (discriminated params + reorder point),
is deterministic (RULE 5), supports (s,S), and returns a clean 422 on bad input.
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


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_returns_typed_policy_and_pir(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/inventory/policy",
        json={"bundle": _bundle_json(), "lead_time_periods": 2.0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    policy = body["policy"]
    assert policy["parameters"]["policy_type"] == "qr"
    assert policy["parameters"]["R"] > 20.0  # E[D_LTD]=20 + safety stock
    assert policy["safety_stock"] > 0
    assert policy["reorder_triggers"][0]["trigger_type"] == "below_reorder_point"
    assert body["pir"]["quantity_planned"] == 10.0  # q50


def test_deterministic_same_request_same_policy(client: TestClient) -> None:
    payload = {"bundle": _bundle_json(), "lead_time_periods": 2.0}
    a = client.post("/api/v1/inventory/policy", json=payload).json()["policy"]
    b = client.post("/api/v1/inventory/policy", json=payload).json()["policy"]
    assert a == b


def test_ss_policy_type(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/inventory/policy",
        json={"bundle": _bundle_json(), "lead_time_periods": 2.0, "policy_type": "ss"},
    )
    assert resp.status_code == 200, resp.text
    params = resp.json()["policy"]["parameters"]
    assert params["policy_type"] == "ss"
    assert params["S"] >= params["s"]


def test_bad_lead_time_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/inventory/policy",
        json={"bundle": _bundle_json(), "lead_time_periods": 0},
    )
    assert resp.status_code == 422  # Field(gt=0)
