"""Single-series forecast API tests — the real (non-synthetic) forecast band.

The endpoint is the lightweight sibling of the leaderboard: one method fit on
the full history, returned synchronously as a real ForecastBundle. These tests
assert the band is real (ordered quantiles, method echoed), deterministic
(RULE 5), open (no tier key), input-bounded, and that bad input yields a clean
422 rather than a 500.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from demand_signal_os.api.app import create_app

# Deterministic seasonal series, long enough for a real fit.
_HISTORY = [10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 3) for i in range(48)]

_REQUEST = {
    "history": _HISTORY,
    "sku_id": "SKU-1",
    "location_id": "DC-1",
    "bucket_period": "day",
    "start_date": "2026-01-01",
    "horizon": 8,
    "season_length": 7,
    "intermittent_mode": "off",
    "method_id": "ets",
    "seed": 42,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_returns_real_ordered_quantile_band(client: TestClient) -> None:
    resp = client.post("/api/v1/forecast/single", json=_REQUEST)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "ets"
    bundle = body["bundle"]
    q = bundle["quantiles"]
    # A real band: quantiles strictly ordered, mean finite, method echoed.
    assert q["q05"] <= q["q25"] <= q["q50"] <= q["q75"] <= q["q95"]
    assert math.isfinite(bundle["mean"])
    assert bundle["method"] == "ets"


def test_deterministic_same_request_same_band(client: TestClient) -> None:
    # RULE 5: the FORECAST values are byte-identical for the same request.
    # (provenance carries a per-bundle UUID + wall-clock produced_at, which are
    # metadata, not forecast output — same as the leaderboard's winner bundle.)
    a = client.post("/api/v1/forecast/single", json=_REQUEST).json()["bundle"]
    b = client.post("/api/v1/forecast/single", json=_REQUEST).json()["bundle"]
    forecast = lambda d: {k: d[k] for k in ("quantiles", "mean", "method", "horizon_label", "distribution")}
    assert forecast(a) == forecast(b)


def test_band_mode_returns_per_step_widening_band(client: TestClient) -> None:
    req = {**_REQUEST, "band": True, "horizon": 8}
    resp = client.post("/api/v1/forecast/single", json=req)
    assert resp.status_code == 200, resp.text
    band = resp.json()["band"]
    assert len(band) == 8
    # every step has an ordered interval, and the interval widens with horizon
    for step in band:
        assert step["q05"] <= step["q50"] <= step["q95"]
    spread = [s["q95"] - s["q05"] for s in band]
    assert spread[-1] >= spread[0]  # uncertainty propagates, not hidden


def test_open_no_tier_key_required(client: TestClient) -> None:
    # No X-API-Key header at all; the preview endpoint must still serve.
    resp = client.post("/api/v1/forecast/single", json={"history": _HISTORY})
    assert resp.status_code == 200, resp.text


def test_history_length_bound_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/forecast/single", json={"history": [1.0] * 521}
    )
    assert resp.status_code == 422  # over _MAX_HISTORY


def test_horizon_bound_rejected(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/forecast/single", json={"history": _HISTORY, "horizon": 61}
    )
    assert resp.status_code == 422  # over _MAX_HORIZON


def test_unknown_method_clean_422(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/forecast/single", json={"history": _HISTORY, "method_id": "not_a_method"}
    )
    assert resp.status_code == 422
    assert "not_a_method" in resp.json()["detail"]
