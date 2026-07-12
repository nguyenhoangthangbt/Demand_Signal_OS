"""Tests for the forecast results-export .xlsx surface.

- unit: ``forecast_to_xlsx`` maps a bundle dict into the right sheets.
- integration: ``POST /api/v1/forecast/single.xlsx`` returns a real workbook.
"""
from __future__ import annotations

import io

import openpyxl
from fastapi.testclient import TestClient

from demand_signal_os.api.app import create_app
from demand_signal_os.api.forecast_export import forecast_to_xlsx

_XLSX_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_RESULT = {
    "method": "ets",
    "bundle": {
        "sku_id": "WORKBENCH", "location_id": "WORKBENCH",
        "horizon_label": "operational",
        "bucket": {"period": "day"},
        "quantiles": {"q05": 47.8, "q10": 48.7, "q25": 50.2, "q50": 51.8,
                      "q75": 53.4, "q90": 54.9, "q95": 55.7},
        "distribution": {"family": "normal", "params": {"mean": 51.8, "std": 2.4}},
        "mean": 51.8, "fallback_applied": None,
        "provenance": {"forecast_bundle_id": "abc", "model_id": "ets-ZZZ-s7",
                       "seed": 42, "feature_set_hash": "deadbeef",
                       "data_cut_timestamp": "2026-01-01T00:00:00Z",
                       "produced_at": "2026-07-12T00:00:00Z"},
    },
    "band": [
        {"h": 1, "q05": 47.8, "q50": 51.8, "q95": 55.7},
        {"h": 2, "q05": 46.1, "q50": 51.9, "q95": 57.4},
    ],
    "band_truncated": False,
}


def test_forecast_to_xlsx_sheets_and_numeric_cells():
    data = forecast_to_xlsx(_RESULT, history=[50, 52, 48, 55])
    assert data[:2] == b"PK"
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Forecast", "Band", "History", "Provenance"]

    fc = wb["Forecast"]  # first sheet -> title row 1, header row 3
    assert fc.cell(row=1, column=1).value == "DemandSignalOS forecast"
    assert fc.cell(row=3, column=1).value == "Quantile"
    assert fc.cell(row=4, column=1).value == "q05"
    assert isinstance(fc.cell(row=4, column=2).value, (int, float))

    band = wb["Band"]  # non-first -> header row 1
    assert band.cell(row=1, column=1).value == "h"
    assert band.cell(row=2, column=1).value == 1

    hist = wb["History"]
    assert hist.cell(row=2, column=2).value == 50


def test_single_forecast_xlsx_endpoint_returns_workbook():
    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/v1/forecast/single.xlsx",
            json={"history": [10, 12, 9, 11, 13, 10, 12, 11, 10, 13, 9, 12],
                  "horizon": 4, "season_length": 4, "method_id": "ets"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == _XLSX_CT
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content[:2] == b"PK"
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        # Forced band=True on the endpoint -> Band sheet always present.
        assert "Forecast" in wb.sheetnames
        assert "Band" in wb.sheetnames
        assert "History" in wb.sheetnames


def test_single_forecast_xlsx_422_on_bad_method():
    with TestClient(create_app()) as client:
        resp = client.post(
            "/api/v1/forecast/single.xlsx",
            json={"history": [1, 2, 3, 4, 5, 6, 7, 8], "method_id": "not_a_method"},
        )
        assert resp.status_code == 422
