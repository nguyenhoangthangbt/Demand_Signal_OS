"""DSO -> SimOS hand-off basis (customer journey 2026-10-12, finding C-01).

Before the fix, every SimOS export read each forecast value as "orders per
day": a monthly forecast of about 2,075 units became about 86.5 orders per hour
(2,075 / 24), about 30x the real load. The customer now states the basis
(period length, orders or units, operating hours), the workbench shows the
converted rate first, and the export header states the conversion.
"""
from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from demand_signal_os.api.app import create_app
from demand_signal_os.api.simos_export import DAYS_PER_MONTH, SimosHandoff

# Persona C's 24 months of seasonal demand (units per month), as pasted live.
MONTHLY = [980, 940, 1050, 1100, 1180, 1120, 1060, 1090, 1250, 1420, 1780, 1950,
           1040, 990, 1110, 1170, 1240, 1190, 1130, 1160, 1330, 1510, 1890, 2080]

# Golden dataset (platforms_os/golden/inputs/dso_demand.json): FACE-CRM, 52
# weeks of units, start 2026-01-01. Copied, not read, to keep the repo standalone.
GOLDEN_FACE_CRM_WEEKS = [
    1185, 1211, 1181, 1291, 1283, 1294, 1232, 1305, 1288, 1263, 1286, 1286, 1292,
    1359, 1119, 1247, 1200, 1256, 1350, 1309, 1334, 1266, 1217, 1228, 1326, 1278,
    1198, 1055, 1046, 1052, 1181, 1210, 1079, 1248, 1059, 1184, 1175, 1144, 1091,
    1129, 1357, 1061, 1158, 1032, 1148, 1217, 1412, 1471, 1317, 1640, 1752, 1854,
]

_BASE = {"horizon": 8, "season_length": 7, "method_id": "ets"}


def _client() -> TestClient:
    return TestClient(create_app())


def _schedule(text: str) -> list[dict]:
    return yaml.safe_load(text)["sources"][0]["arrivals"]["schedule"]


def test_hours_per_period_basis():
    assert SimosHandoff(data_frequency="day").hours_per_period() == 24.0
    assert SimosHandoff(data_frequency="week").hours_per_period() == 168.0
    assert SimosHandoff(data_frequency="month").hours_per_period() == pytest.approx(730.5)
    two_shift = SimosHandoff(data_frequency="month", operating_hours_per_day=16,
                             operating_days_per_week=5)
    assert two_shift.hours_per_period() == pytest.approx(16 * 5 * DAYS_PER_MONTH / 7)
    assert SimosHandoff(data_frequency="week", demand_unit="units",
                        units_per_order=2.5).units_per_entity() == 2.5
    # units_per_order only applies when the series counts units.
    assert SimosHandoff(data_frequency="week", units_per_order=2.5).units_per_entity() == 1.0


def test_monthly_forecast_becomes_rate_per_operating_hour():
    """C-01 regression: a monthly series must not be read as daily."""
    with _client() as c:
        preview = c.post("/api/v1/forecast/single.simos.preview", json={
            **_BASE, "history": MONTHLY,
            "handoff": {"data_frequency": "month", "demand_unit": "orders"},
        })
        assert preview.status_code == 200, preview.text
        p = preview.json()
        first = p["steps"][0]
        # orders per month / 730.5 h, not / 24 h.
        assert first["rate_per_hour"] == pytest.approx(first["forecast_median"] / 730.5)
        assert first["rate_per_hour"] < 5.0  # was about 86 before the fix
        assert p["hours_per_period"] == pytest.approx(730.5)
        assert "per month" in p["explanation"]
        # Period i starts at i x 730.5 operating hours.
        assert p["steps"][1]["starts_at_hour"] == pytest.approx(730.5)

        yml = c.post("/api/v1/forecast/single.yaml", json={
            **_BASE, "history": MONTHLY,
            "handoff": {"data_frequency": "month", "demand_unit": "orders"},
        })
        assert yml.status_code == 200
        sched = _schedule(yml.text)
        # The download carries exactly the numbers the customer confirmed.
        assert [e["rate_per_hour"] for e in sched] == [s["rate_per_hour"] for s in p["steps"]]
        assert sched[1]["time"] == pytest.approx(730.5 * 3600)
        assert "# Conversion: Each forecast value is orders per month" in yml.text


def test_units_and_shift_hours_scale_the_rate():
    body = {**_BASE, "history": MONTHLY}
    with _client() as c:
        orders = c.post("/api/v1/forecast/single.simos.preview", json={
            **body, "handoff": {"data_frequency": "month"}}).json()
        units = c.post("/api/v1/forecast/single.simos.preview", json={
            **body, "handoff": {"data_frequency": "month", "demand_unit": "units",
                                "units_per_order": 2}}).json()
        shifts = c.post("/api/v1/forecast/single.simos.preview", json={
            **body, "handoff": {"data_frequency": "month",
                                "operating_hours_per_day": 16,
                                "operating_days_per_week": 5}}).json()
    r0 = orders["steps"][0]["rate_per_hour"]
    assert units["steps"][0]["rate_per_hour"] == pytest.approx(r0 / 2)
    assert shifts["steps"][0]["rate_per_hour"] == pytest.approx(r0 * 730.5 / (16 * 5 * DAYS_PER_MONTH / 7))
    assert "with 2 units per order" in units["explanation"]


def test_simos_xlsx_carries_the_stated_basis():
    with _client() as c:
        p = c.post("/api/v1/forecast/single.simos.preview", json={
            **_BASE, "history": MONTHLY, "handoff": {"data_frequency": "month"}}).json()
        r = c.post("/api/v1/forecast/single.simos.xlsx", json={
            **_BASE, "history": MONTHLY, "handoff": {"data_frequency": "month"}})
    assert r.status_code == 200
    from excel_io import ARRIVAL_SCHEDULE_SHEET, arrivals_schedule_spec, parse_xlsx

    vals, _errs = parse_xlsx(arrivals_schedule_spec(), r.content)
    rows = vals[ARRIVAL_SCHEDULE_SHEET]
    assert [row["rate_per_hour"] for row in rows] == pytest.approx(
        [s["rate_per_hour"] for s in p["steps"]])
    assert rows[1]["time"] == pytest.approx(730.5 * 3600)


def test_no_basis_keeps_the_old_daily_reading_and_says_so():
    """API callers that send no basis get the pre-fix numbers, and the header
    now states the reading instead of hiding it."""
    with _client() as c:
        r = c.post("/api/v1/forecast/single.yaml", json={**_BASE, "history": MONTHLY})
        p = c.post("/api/v1/forecast/single.simos.preview",
                   json={**_BASE, "history": MONTHLY}).json()
    sched = _schedule(r.text)
    assert sched[0]["rate_per_hour"] == pytest.approx(p["steps"][0]["forecast_median"] / 24.0)
    assert sched[1]["time"] == 86400.0
    assert "orders per day" in r.text


def test_handoff_export_is_byte_deterministic():
    """RULE 5: same series + basis -> byte-identical YAML."""
    body = {**_BASE, "history": GOLDEN_FACE_CRM_WEEKS, "start_date": "2026-01-01",
            "handoff": {"data_frequency": "week", "demand_unit": "units",
                        "units_per_order": 1.0, "operating_hours_per_day": 16,
                        "operating_days_per_week": 6}}
    with _client() as c:
        a = c.post("/api/v1/forecast/single.yaml", json=body)
        b = c.post("/api/v1/forecast/single.yaml", json=body)
    assert a.status_code == 200
    assert a.content == b.content


def test_golden_face_crm_weekly_handoff_baseline():
    """E2E baseline on the golden FACE-CRM series: weekly units -> SimOS orders
    per operating hour (16 h x 6 d = 96 h a week). Pinned values catch drift."""
    body = {**_BASE, "history": GOLDEN_FACE_CRM_WEEKS, "start_date": "2026-01-01",
            "handoff": {"data_frequency": "week", "demand_unit": "units",
                        "units_per_order": 1.0, "operating_hours_per_day": 16,
                        "operating_days_per_week": 6}}
    with _client() as c:
        p = c.post("/api/v1/forecast/single.simos.preview", json=body).json()
        y = c.post("/api/v1/forecast/single.yaml", json=body)
    assert p["hours_per_period"] == 96.0
    first = p["steps"][0]
    assert first["rate_per_hour"] == pytest.approx(first["forecast_median"] / 96.0)
    assert round(first["forecast_median"], 6) == GOLDEN_FIRST_MEDIAN
    assert round(first["rate_per_hour"], 6) == GOLDEN_FIRST_RATE
    sched = _schedule(y.text)
    assert len(sched) == 8
    assert [e["time"] for e in sched] == [i * 96.0 * 3600 for i in range(8)]
    for e in sched:  # SimOS ScheduleEntry contract: finite, non-negative.
        assert e["rate_per_hour"] >= 0 and 0 <= e["noise_std"] <= e["rate_per_hour"] / 3


# Pinned from the first run on 2026-10-13 (ets, seed 42, horizon 8).
GOLDEN_FIRST_MEDIAN = 1795.99567
GOLDEN_FIRST_RATE = 18.708288


def test_leaderboard_arrivals_handoff_query_validation():
    """Bad hand-off settings on the leaderboard export give a plain 422."""
    from demand_signal_os.api.leaderboard_routes import _handoff_from_query
    from fastapi import HTTPException

    assert _handoff_from_query(None, "orders", 1.0, 24.0, 7.0) is None
    h = _handoff_from_query("month", "units", 3.0, 16.0, 5.0)
    assert h.units_per_entity() == 3.0
    with pytest.raises(HTTPException) as exc:
        _handoff_from_query("month", "orders", 1.0, 30.0, 7.0)
    assert exc.value.status_code == 422
    assert "hours a day 0 to 24" in exc.value.detail


@pytest.mark.parametrize("origin", ["https://planning.sim-os.ai", "https://planning.plan2cash.com"])
def test_planning_workbench_may_call_the_forecast(origin):
    """PlanningOS "Use a DSO forecast" (journey C-03) calls /forecast/single
    from the planning workbench in the browser; CORS must allow it."""
    with _client() as c:
        r = c.options("/api/v1/forecast/single", headers={
            "Origin": origin, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == origin
