"""Multi-SKU batch forecast route (audit findings C-08 / F-03).

``POST /forecast/batch`` takes ONE uploaded file (CSV, the demand_history or
demand_history_multi template, or any xlsx table with SKU / location / period /
demand columns) and returns a probabilistic forecast band per (SKU, location)
series, using the same settings resolution as the quick forecast (season and
method can be ``"auto"``).

The file is posted as the raw request body (``application/octet-stream``,
``text/csv`` or the xlsx media type), not as multipart, so the API image needs
no extra form-parsing dependency.

Gated like the leaderboard (``require_dso_access``: Premium and up, or a
``dso_live_`` key). Deterministic (RULE 5): same file + same query = same
bands; the data cut is the fixed ``start_date``, never the wall clock.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from demand_signal_os.api.auth import require_dso_access

router = APIRouter(tags=["forecast"], dependencies=[Depends(require_dso_access)])

_MAX_BATCH_HORIZON = 24  # same per-step cap as the quick forecast band
_MIN_POINTS = 4


def _season_param(raw: str) -> int | Literal["auto"]:
    if raw == "auto":
        return "auto"
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise HTTPException(
            status_code=422,
            detail="Season length must be auto or a whole number of periods (1 or more).",
        )
    return value


def _forecast_one(
    sku_id: str,
    location_id: str,
    values: list[float],
    *,
    horizon: int,
    season: int | Literal["auto"],
    method_id: str,
    seed: int,
) -> dict[str, Any]:
    """Fit one series. Problems come back as a plain ``error`` on that series,
    so one bad SKU never sinks the whole file."""
    from demand_signal_os.api.forecast_routes import (
        SingleForecastRequest,
        _build_actuals,
        _build_config,
    )
    from demand_signal_os.leaderboard import forecast_path

    out: dict[str, Any] = {"sku_id": sku_id, "location_id": location_id, "n_points": len(values)}
    if len(values) < _MIN_POINTS:
        out["error"] = f"Needs at least {_MIN_POINTS} periods of history; this series has {len(values)}."
        return out
    if len(values) > 520:
        values = values[-520:]
        out["note"] = "Only the latest 520 periods were used."
    try:
        req = SingleForecastRequest(
            history=values, sku_id=sku_id or "SKU", location_id=location_id or "ALL",
            horizon=horizon, season_length=season, method_id=method_id, seed=seed,
        )
        path = forecast_path(_build_actuals(req), _build_config(req), req.method_id)
    except Exception:  # noqa: BLE001 - plain per-series message, never a raw error
        out["error"] = (
            "This series could not be forecast. Check for long runs of zeros or "
            "missing periods, or try a shorter season length."
        )
        return out
    out["settings"] = req.settings()
    out["method"] = req.method_id
    out["band"] = [
        {"h": i + 1, "q05": round(q.q05, 3), "q50": round(q.q50, 3), "q95": round(q.q95, 3)}
        for i, q in enumerate(path)
    ]
    return out


@router.post("/forecast/batch")
async def batch_forecast(
    request: Request,
    horizon: int = Query(default=8, ge=1, le=_MAX_BATCH_HORIZON),
    season_length: str = Query(default="auto"),
    method_id: str = Query(default="auto"),
    seed: int = Query(default=42),
) -> dict[str, Any]:
    """Forecast every (SKU, location) series in one uploaded file."""
    from demand_signal_os.api.batch_input import BatchInputError, parse_batch_file

    from demand_signal_os.forecasting.registry import REGISTERED_IDS

    if method_id != "auto" and method_id not in REGISTERED_IDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown method '{method_id}'. Use auto or one of: {', '.join(REGISTERED_IDS)}.",
        )
    season = _season_param(season_length)
    data = await request.body()
    try:
        parsed = parse_batch_file(data)
    except BatchInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    results = [
        {
            **_forecast_one(
                s.sku_id, s.location_id, s.values,
                horizon=horizon, season=season, method_id=method_id, seed=seed,
            ),
            "history": s.values,
            "periods": s.periods,
        }
        for s in parsed.series
    ]
    return {
        "source_format": parsed.source_format,
        "n_series": len(results),
        "n_forecast": sum(1 for r in results if "band" in r),
        "skipped_rows": parsed.skipped_rows,
        "horizon": horizon,
        "series": results,
    }
