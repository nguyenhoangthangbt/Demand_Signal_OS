"""Single-series forecast route (v0.2 — real forecast band).

The forecaster LEADERBOARD (``leaderboard_routes``) runs the heavy walk-forward
panel (every registered method, N windows) and is gated + backgrounded. This
route is its lightweight sibling: ONE chosen method fit on the full history,
returned SYNCHRONOUSLY as a real ``ForecastBundle`` (q05-q95). It powers the
public workbench forecast preview, replacing the v0.1 hardcoded synthetic band.

A single fit is sub-second, so the endpoint is OPEN (no tier key) and bounds
per-call compute via input limits (history length, horizon). Flip to gated by
adding ``dependencies=[Depends(require_api_key)]`` if abuse appears.

Determinism (RULE 5): the data cut is derived from ``start_date`` (default
fixed), never the wall clock, so the same request yields a byte-identical band.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["forecast"])

_MAX_HISTORY = 520  # ~10y weekly / ~1.4y daily — bounds per-call compute
_MAX_HORIZON = 60
_MAX_BAND = 24  # band mode fits once per step; cap the per-step fits


class SingleForecastRequest(BaseModel):
    """One series + a chosen method -> one real probabilistic forecast."""

    history: list[float] = Field(
        min_length=1, max_length=_MAX_HISTORY, description="observed units in time order"
    )
    sku_id: str = "WORKBENCH"
    location_id: str = "WORKBENCH"
    bucket_period: Literal["day", "week"] = "day"
    # Fixed default keeps the run deterministic (RULE 5) for the preview.
    start_date: date = date(2026, 1, 1)
    horizon: int = Field(default=12, ge=1, le=_MAX_HORIZON)
    season_length: int = Field(default=7, ge=1)
    intermittent_mode: Literal["auto", "on", "off"] = "auto"
    method_id: str = "ets"
    seed: int = 42
    # When true, also return per-step quantiles (h=1..horizon) so the caller can
    # draw the widening band. Each step is a terminal-horizon fit, so this is
    # ``horizon`` fits; bounded by _MAX_BAND to keep the preview snappy.
    band: bool = False


def _build_actuals(body: SingleForecastRequest) -> list[Any]:
    """DemandActual records from the posted series (mirrors leaderboard_routes)."""
    from demand_signal_os.ops_schemas import CensoringFlag, DemandActual, TimeBucket

    records: list[Any] = []
    for i, value in enumerate(body.history):
        if body.bucket_period == "day":
            d = body.start_date + timedelta(days=i)
            bucket = TimeBucket(period="day", start=d, end=d + timedelta(days=1))
        else:
            d = body.start_date + timedelta(weeks=i)
            bucket = TimeBucket(period="week", start=d, end=d + timedelta(weeks=1))
        records.append(
            DemandActual(
                sku_id=body.sku_id,
                location_id=body.location_id,
                bucket=bucket,
                units_sold=float(value),
                units_demanded=float(value),
                censoring=CensoringFlag.REAL_ZERO if value == 0 else CensoringFlag.UNKNOWN,
                source_system="api",
                recorded_at=datetime.combine(bucket.end, time.min, tzinfo=UTC),
            )
        )
    return records


def _build_config(body: SingleForecastRequest, horizon: int | None = None) -> Any:
    from demand_signal_os.leaderboard import LeaderboardConfig

    return LeaderboardConfig(
        sku_id=body.sku_id,
        location_id=body.location_id,
        horizon=horizon if horizon is not None else body.horizon,
        season_length=body.season_length,
        intermittent_mode=body.intermittent_mode,
        seed=body.seed,
        data_cut_timestamp=datetime.combine(body.start_date, time.min, tzinfo=UTC),
    )


def _compute_forecast(body: SingleForecastRequest) -> dict[str, Any]:
    """Fit one method on the full history -> the ``/forecast/single`` response
    dict (``{"method", "bundle", optional "band", "band_truncated"}``). Raises
    a clean 422 on any forecaster failure so callers never see a 500."""
    from demand_signal_os.leaderboard import fit_winner_bundle

    actuals = _build_actuals(body)

    def _fit(horizon: int) -> Any:
        cfg = _build_config(body, horizon=horizon)
        return fit_winner_bundle(actuals, cfg, body.method_id)

    try:
        bundle = _fit(body.horizon)
        out: dict[str, Any] = {
            "method": body.method_id,
            "bundle": bundle.model_dump(mode="json"),
        }
        if body.band:
            from demand_signal_os.leaderboard import forecast_path

            steps = min(body.horizon, _MAX_BAND)
            path = forecast_path(actuals, _build_config(body, horizon=steps), body.method_id)
            out["band"] = [
                {"h": i + 1, "q05": q.q05, "q50": q.q50, "q95": q.q95}
                for i, q in enumerate(path)
            ]
            out["band_truncated"] = body.horizon > _MAX_BAND
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface a clean 422, not a 500
        raise HTTPException(
            status_code=422,
            detail=(
                f"forecast failed for method '{body.method_id}': "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc
    return out


@router.post("/forecast/single")
async def single_forecast(body: SingleForecastRequest) -> dict[str, Any]:
    """Fit one method on the full history -> a real ``ForecastBundle`` (q05-q95).

    Synchronous (one fit, sub-second). Returns 422 if the series is too short
    for the method or ``method_id`` is unknown, so the caller gets a clear
    reason rather than a 500.
    """
    return _compute_forecast(body)


@router.post("/forecast/single.xlsx")
async def single_forecast_xlsx(body: SingleForecastRequest) -> StreamingResponse:
    """The forecast as a native .xlsx workbook (terminal quantiles + per-step
    widening band + posted history + provenance) — the Excel peer of the CSV
    download, for offline validation. Forces the band on so the workbook always
    carries the widening interval the customer validates."""
    from demand_signal_os.api.forecast_export import forecast_to_xlsx

    body_with_band = body.model_copy(update={"band": True})
    result = _compute_forecast(body_with_band)
    xlsx = forecast_to_xlsx(result, body.history)
    return StreamingResponse(
        io.BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=forecast.xlsx"},
    )


@router.post("/forecast/single.yaml")
async def single_forecast_arrivals_yaml(body: SingleForecastRequest) -> StreamingResponse:
    """The DSO→SimOS contract for this forecast: a SimOS ``arrivals.schedule``
    YAML block (one entry per horizon step) that SimOS consumes directly. Humans
    audit the .xlsx; SimOS ingests this YAML."""
    from demand_signal_os.api.simos_export import forecast_to_simos_arrivals_yaml
    from demand_signal_os.leaderboard import fit_winner_bundle, forecast_path

    actuals = _build_actuals(body)
    cfg = _build_config(body)
    try:
        winner_bundle = fit_winner_bundle(actuals, cfg, body.method_id)
        path = forecast_path(actuals, cfg, body.method_id)
    except Exception as exc:  # noqa: BLE001 — clean 422, not a 500
        raise HTTPException(
            status_code=422,
            detail=f"forecast failed for method '{body.method_id}': "
                   f"{type(exc).__name__}: {exc}",
        ) from exc
    text = forecast_to_simos_arrivals_yaml(
        winner_bundle, path,
        bucket_period=body.bucket_period, start_date=body.start_date,
    )
    return StreamingResponse(
        io.BytesIO(text.encode("utf-8")),
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=arrivals.yaml"},
    )
