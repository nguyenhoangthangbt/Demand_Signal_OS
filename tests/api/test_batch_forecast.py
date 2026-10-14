"""Multi-SKU batch forecast from one uploaded file (audit C-08 / F-03).

Before: no route accepted a file; the quick forecast took one pasted series,
everything was recorded as ``sku_id: WORKBENCH``, and plan2cash.com's
"Run forecast" ignored a validated demand_history workbook ("Batch-forecasting
your full uploaded history is on the roadmap").
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from excel_io import generate_xlsx

from demand_signal_os.api.app import create_app
from demand_signal_os.api.batch_input import BatchInputError, parse_batch_file
from demand_signal_os.builder.schemas import DEMAND_HISTORY_MULTI_SCHEMA, DEMAND_HISTORY_SCHEMA

MARCO_MONTHLY = [
    980, 940, 1050, 1100, 1180, 1120, 1060, 1090, 1250, 1420, 1780, 1950,
    1040, 990, 1110, 1170, 1240, 1190, 1130, 1160, 1330, 1510, 1890, 2080,
]


def _month(i: int) -> str:
    return f"{2024 + i // 12}-{i % 12 + 1:02d}-01"


def _csv() -> bytes:
    lines = ["sku_id,location_id,period,units"]
    for sku, scale in (("FACE-CRM", 1.0), ("SERUM-30", 0.5)):
        for dc in ("DC-NORTH", "DC-SOUTH"):
            for i, v in enumerate(MARCO_MONTHLY):
                lines.append(f"{sku},{dc},{_month(i)},{round(v * scale)}")
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def _post(client: TestClient, data: bytes, **params) -> object:
    return client.post(
        "/api/v1/forecast/batch",
        content=data,
        params={"horizon": 12, **params},
        headers={"Content-Type": "application/octet-stream"},
    )


def test_csv_with_four_series_forecasts_each(client: TestClient) -> None:
    resp = _post(client, _csv())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_format"] == "csv"
    assert body["n_series"] == 4 and body["n_forecast"] == 4
    keys = [(s["sku_id"], s["location_id"]) for s in body["series"]]
    assert keys == [
        ("FACE-CRM", "DC-NORTH"), ("FACE-CRM", "DC-SOUTH"),
        ("SERUM-30", "DC-NORTH"), ("SERUM-30", "DC-SOUTH"),
    ]
    first = body["series"][0]
    assert first["settings"]["season_length"] == 12  # season inferred per series
    assert len(first["band"]) == 12
    q50 = [b["q50"] for b in first["band"]]
    assert q50[11] > 1.6 * q50[0]  # follows the Q4 peak, not flat


def test_demand_history_multi_template_is_read(client: TestClient) -> None:
    rows = [
        {"sku_id": sku, "location_id": "DC-1", "period_label": _month(i),
         "observed_demand": float(v), "censoring_flag": "OBSERVED"}
        for sku in ("A", "B") for i, v in enumerate(MARCO_MONTHLY)
    ]
    xlsx = generate_xlsx(DEMAND_HISTORY_MULTI_SCHEMA, values={},
                         tabular_rows={"observations": rows})
    body = _post(client, xlsx).json()
    assert body["source_format"] == "demand_history_multi"
    assert [s["sku_id"] for s in body["series"]] == ["A", "B"]
    assert all("band" in s for s in body["series"])


def test_single_sku_demand_history_template_is_read(client: TestClient) -> None:
    rows = [
        {"period_label": _month(i), "observed_demand": float(v), "censoring_flag": "OBSERVED"}
        for i, v in enumerate(MARCO_MONTHLY)
    ]
    xlsx = generate_xlsx(DEMAND_HISTORY_SCHEMA, values={"sku_id": "FACE-CRM", "location_id": "DC-7"},
                         tabular_rows={"History": rows})
    body = _post(client, xlsx).json()
    assert body["source_format"] == "demand_history"
    s = body["series"][0]
    assert (s["sku_id"], s["location_id"], s["n_points"]) == ("FACE-CRM", "DC-7", 24)


def test_dates_out_of_order_are_sorted(client: TestClient) -> None:
    lines = ["sku,date,demand"] + [f"X,{_month(i)},{v}" for i, v in reversed(list(enumerate(MARCO_MONTHLY)))]
    parsed = parse_batch_file(("\n".join(lines)).encode())
    assert parsed.series[0].values == [float(v) for v in MARCO_MONTHLY]


def test_short_series_gets_a_plain_per_series_message(client: TestClient) -> None:
    data = b"sku_id,units\nA,5\nA,6\nB," + b"\nB,".join(str(v).encode() for v in MARCO_MONTHLY) + b"\n"
    body = _post(client, data).json()
    a = next(s for s in body["series"] if s["sku_id"] == "A")
    assert "at least 4 periods" in a["error"] and "band" not in a
    assert body["n_forecast"] == 1


@pytest.mark.parametrize(
    ("data", "needle"),
    [
        (b"", "empty"),
        (b"foo,bar\n1,2\n", "demand column"),
        (b"period,units\n1,5\n", "SKU column"),
        (b"PK\x03\x04not really a zip", "Excel workbook"),
    ],
)
def test_unreadable_files_get_plain_422(client: TestClient, data: bytes, needle: str) -> None:
    resp = _post(client, data)
    assert resp.status_code == 422
    assert needle in resp.json()["detail"]


def test_bad_query_values_are_plain(client: TestClient) -> None:
    assert "Season length" in _post(client, _csv(), season_length="x").json()["detail"]
    assert "Unknown method" in _post(client, _csv(), method_id="nope").json()["detail"]


def test_batch_is_deterministic(client: TestClient) -> None:
    a = _post(client, _csv()).json()
    b = _post(client, _csv()).json()
    assert a == b


def test_batch_requires_access_when_keys_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DSO_API_KEYS", "dso_live_test")
    c = TestClient(create_app())
    assert _post(c, _csv()).status_code == 401


def test_parse_rejects_too_many_series() -> None:
    lines = ["sku,units"] + [f"S{i},1" for i in range(201)]
    with pytest.raises(BatchInputError):
        parse_batch_file("\n".join(lines).encode())
