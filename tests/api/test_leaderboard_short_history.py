"""Two years of monthly history must get a plain message, not a raw
``ValueError`` (audit finding C-07).

Before: 24 points with season 12 / horizon 6 (the UI sends min_train_size 24)
queued a run that failed with ``ValueError: history_length 24 too small for
min_train_size 24 + horizon_size 6``, shown verbatim on the leaderboard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from demand_signal_os.api import leaderboard_routes
from demand_signal_os.api.app import create_app
from demand_signal_os.api.leaderboard_routes import history_shortfall_message

MARCO_MONTHLY = [
    980, 940, 1050, 1100, 1180, 1120, 1060, 1090, 1250, 1420, 1780, 1950,
    1040, 990, 1110, 1170, 1240, 1190, 1130, 1160, 1330, 1510, 1890, 2080,
]

# Exactly the request the leaderboard page sent for persona C.
_SHORT = {
    "sku_id": "WORKBENCH",
    "location_id": "WORKBENCH",
    "history": MARCO_MONTHLY,
    "bucket_period": "day",
    "start_date": "2026-01-01",
    "horizon": 6,
    "season_length": 12,
    "intermittent_mode": "auto",
    "forecaster_set": "all",
    "n_windows": 2,
    "min_train_size": 24,
    "seed": 42,
}

_RAW_MARKERS = ("ValueError", "history_length", "horizon_size", "Traceback")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_short_history_is_refused_with_a_plain_sentence(client: TestClient) -> None:
    resp = client.post("/api/v1/forecast/leaderboard", json=_SHORT)
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert not any(m in detail for m in _RAW_MARKERS), detail
    assert "24 periods" in detail and "at least 30" in detail


def test_failed_run_error_is_plain(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    # Any engine failure that does get past the guard still shows a plain
    # sentence; the technical reason is kept separately for support.
    def boom(*_a, **_k):
        raise ValueError("history_length 30 too small for min_train_size 24 + horizon_size 6")

    monkeypatch.setattr("demand_signal_os.leaderboard.orchestrate", boom)
    req = {**_SHORT, "history": MARCO_MONTHLY + MARCO_MONTHLY[:6]}  # 30 points, passes guard
    run_id = client.post("/api/v1/forecast/leaderboard", json=req).json()["run_id"]
    body = client.get(f"/api/v1/forecast/leaderboard/{run_id}").json()
    assert body["status"] == "failed"
    assert not any(m in body["error"] for m in _RAW_MARKERS), body["error"]
    assert "ValueError" in leaderboard_routes._RUNS[run_id]["error_detail"]


def test_shortfall_message_none_when_enough_history() -> None:
    assert history_shortfall_message(30, 24, 6) is None
    assert history_shortfall_message(29, 24, 6) is not None
