"""Leaderboard API tests — submit/poll/winner/receipt + auth.

A small config keeps the heavy GBM path fast. Starlette's TestClient runs
BackgroundTasks synchronously before the POST returns, so the run is already
complete when submit_leaderboard responds.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from demand_signal_os.api.app import create_app

# Deterministic seasonal-ish series, dense (no intermittency), long enough for
# 2 windows of horizon 4 with min_train_size 24 and GBM lag/rolling features.
_HISTORY = [
    10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 3) for i in range(48)
]

_REQUEST = {
    "sku_id": "SKU-1",
    "location_id": "DC-1",
    "history": _HISTORY,
    "bucket_period": "day",
    "start_date": "2026-01-01",
    "horizon": 4,
    "season_length": 7,
    "intermittent_mode": "off",
    "n_windows": 2,
    "min_train_size": 24,
    "seed": 42,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def completed_run(client: TestClient) -> str:
    resp = client.post("/api/v1/forecast/leaderboard", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    return resp.json()["run_id"]


def test_health(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["engine"] == "demandsignal"


def test_submit_returns_run_id(completed_run: str) -> None:
    assert completed_run.startswith("lb_")


def test_poll_returns_ranked_result(client: TestClient, completed_run: str) -> None:
    resp = client.get(f"/api/v1/forecast/leaderboard/{completed_run}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "complete"
    result = body["result"]
    # off-mode: ets, gbm, arima, theta, ces + 3 benchmarks
    assert result["n_methods"] == 8
    ranks = [e["rank"] for e in result["entries"]]
    assert ranks == sorted(ranks)
    assert result["entries"][0]["rank"] == 1


def test_winner_returns_bundle(client: TestClient, completed_run: str) -> None:
    resp = client.get(f"/api/v1/forecast/leaderboard/{completed_run}/winner")
    assert resp.status_code == 200
    body = resp.json()
    assert body["winner_method_id"]
    bundle = body["bundle"]
    # Bundle-ready: has quantiles + method + provenance for the downstream bundle.
    assert "quantiles" in bundle
    assert bundle["method"] == body["winner_method_id"]
    assert bundle["quantiles"]["q05"] <= bundle["quantiles"]["q95"]


def test_receipt_is_signed(client: TestClient, completed_run: str) -> None:
    resp = client.get(f"/api/v1/forecast/leaderboard/{completed_run}/receipt")
    assert resp.status_code == 200
    receipt = resp.json()
    # Signed trust receipt carries an HMAC signature.
    assert receipt.get("signature")
    # Checks live in phases[].metrics[]; the benchmark gate must be present.
    names = {
        m["name"] for ph in receipt["phases"] for m in ph["metrics"]
    }
    assert any("beats all benchmarks" in n for n in names)


def test_receipt_is_deterministic(client: TestClient, completed_run: str) -> None:
    a = client.get(f"/api/v1/forecast/leaderboard/{completed_run}/receipt").json()
    b = client.get(f"/api/v1/forecast/leaderboard/{completed_run}/receipt").json()
    # Same run -> byte-identical signed receipt (RULE 5).
    assert a["calibration_id"] == b["calibration_id"]
    assert a["signature"] == b["signature"]


def test_idempotent_run_id(client: TestClient, completed_run: str) -> None:
    resp = client.post("/api/v1/forecast/leaderboard", json=_REQUEST)
    assert resp.json()["run_id"] == completed_run


def test_unknown_run_404(client: TestClient) -> None:
    resp = client.get("/api/v1/forecast/leaderboard/lb_doesnotexist")
    assert resp.status_code == 404


def test_auth_enforced_when_keys_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSO_API_KEYS", "dso_live_secret123")
    authed_client = TestClient(create_app())
    # No key -> 401
    resp = authed_client.get("/api/v1/forecast/leaderboard/lb_whatever")
    assert resp.status_code == 401
    # Valid key -> passes auth (404 because run doesn't exist, not 401)
    resp = authed_client.get(
        "/api/v1/forecast/leaderboard/lb_whatever",
        headers={"X-API-Key": "dso_live_secret123"},
    )
    assert resp.status_code == 404
