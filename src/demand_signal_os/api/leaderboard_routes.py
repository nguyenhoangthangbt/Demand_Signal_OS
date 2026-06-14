"""Forecast-leaderboard routes (the v0.1.5 API extraction).

Unlike the trust-gate routes, these run the HEAVY DSO stack (the orchestrator
fits every registered method through the walk-forward harness). Because a full
panel can take minutes, the run is a BACKGROUND JOB:

    POST /forecast/leaderboard          -> {run_id, status: "queued"}
    GET  /forecast/leaderboard/{id}     -> {status, result?}
    GET  /forecast/leaderboard/{id}/receipt -> signed reproducibility receipt
    GET  /forecast/leaderboard/{id}/winner  -> bundle-ready ForecastBundle

The run is deterministic in the request (RULE 5): ``data_cut_timestamp`` is
derived from ``start_date``, never the wall clock, and ``run_id`` is a hash of
the canonical request — so resubmitting the same request is idempotent.

Imports of the heavy stack stay inside handlers so the app module stays light.
Auth: tier key via ``require_api_key`` (open in dev when DSO_API_KEYS unset).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from demand_signal_os.api.auth import require_api_key

router = APIRouter(tags=["leaderboard"], dependencies=[Depends(require_api_key)])

# In-memory run store (single-process v0.1.5). run_id -> job dict.
_RUNS: dict[str, dict[str, Any]] = {}


class LeaderboardRunRequest(BaseModel):
    """Self-serve leaderboard request — the four user knobs + the series."""

    sku_id: str
    location_id: str
    history: list[float] = Field(min_length=1, description="observed units in time order")
    bucket_period: Literal["day", "week"] = "day"
    start_date: date
    # The four bounded knobs (NOT an AutoML search):
    horizon: int = Field(default=10, ge=1)
    season_length: int = Field(default=12, ge=1)
    intermittent_mode: Literal["auto", "on", "off"] = "auto"
    quantile_levels: list[float] | None = None
    # Engine controls (sensible defaults):
    seed: int = 42
    n_windows: int = Field(default=4, ge=1)
    min_train_size: int = Field(default=24, ge=1)
    min_quantile_spread: float | None = Field(default=None, ge=0.0)


def _run_id(body: LeaderboardRunRequest) -> str:
    blob = json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return "lb_" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _bucket_for(start: date, idx: int, period: str) -> Any:
    from demand_signal_os.ops_schemas import TimeBucket

    if period == "day":
        d = start + timedelta(days=idx)
        return TimeBucket(period="day", start=d, end=d + timedelta(days=1))
    d = start + timedelta(weeks=idx)
    return TimeBucket(period="week", start=d, end=d + timedelta(weeks=1))


def _build_actuals(body: LeaderboardRunRequest) -> list[Any]:
    """Reconstruct DemandActual records from the posted series.

    The harness reads only (units_sold, bucket); censoring is set for schema
    validity and does not influence ranking.
    """
    from demand_signal_os.ops_schemas import CensoringFlag, DemandActual

    records = []
    for i, value in enumerate(body.history):
        bucket = _bucket_for(body.start_date, i, body.bucket_period)
        records.append(
            DemandActual(
                sku_id=body.sku_id,
                location_id=body.location_id,
                bucket=bucket,
                units_sold=float(value),
                units_demanded=float(value),
                censoring=CensoringFlag.REAL_ZERO
                if value == 0
                else CensoringFlag.UNKNOWN,
                source_system="api",
                recorded_at=datetime.combine(bucket.end, time.min, tzinfo=UTC),
            )
        )
    return records


def _build_config(body: LeaderboardRunRequest) -> Any:
    from demand_signal_os.leaderboard import LeaderboardConfig

    kwargs: dict[str, Any] = dict(
        sku_id=body.sku_id,
        location_id=body.location_id,
        horizon=body.horizon,
        season_length=body.season_length,
        intermittent_mode=body.intermittent_mode,
        seed=body.seed,
        n_windows=body.n_windows,
        min_train_size=body.min_train_size,
        min_quantile_spread=body.min_quantile_spread,
        # Determinism: derive the data cut from the input, not the wall clock.
        data_cut_timestamp=datetime.combine(body.start_date, time.min, tzinfo=UTC),
    )
    if body.quantile_levels is not None:
        kwargs["quantile_levels"] = body.quantile_levels
    return LeaderboardConfig(**kwargs)


def _execute(run_id: str, body: LeaderboardRunRequest) -> None:
    """Background worker — runs the orchestrator and stores the result."""
    from demand_signal_os.leaderboard import orchestrate

    try:
        actuals = _build_actuals(body)
        config = _build_config(body)
        result = orchestrate(actuals, config)
        _RUNS[run_id].update(status="complete", result=result)
    except Exception as exc:  # noqa: BLE001 — surface any engine failure to the client
        _RUNS[run_id].update(status="failed", error=f"{type(exc).__name__}: {exc}")


@router.post("/forecast/leaderboard")
async def submit_leaderboard(
    body: LeaderboardRunRequest, background: BackgroundTasks
) -> dict[str, Any]:
    """Queue a leaderboard run. Idempotent: same request -> same run_id."""
    run_id = _run_id(body)
    existing = _RUNS.get(run_id)
    if existing is None or existing["status"] == "failed":
        _RUNS[run_id] = {"status": "queued", "request": body, "result": None, "error": None}
        background.add_task(_execute, run_id, body)
    return {"run_id": run_id, "status": _RUNS[run_id]["status"]}


def _get_run(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id {run_id}")
    return run


@router.get("/forecast/leaderboard/{run_id}")
async def get_leaderboard(run_id: str) -> dict[str, Any]:
    """Poll a run. Returns the ranked LeaderboardResult once complete."""
    run = _get_run(run_id)
    out: dict[str, Any] = {"run_id": run_id, "status": run["status"]}
    if run["status"] == "complete":
        out["result"] = run["result"].model_dump(mode="json")
    elif run["status"] == "failed":
        out["error"] = run["error"]
    return out


@router.get("/forecast/leaderboard/{run_id}/winner")
async def get_winner(run_id: str) -> dict[str, Any]:
    """Bundle-ready ForecastBundle from the winning method (full-history fit)."""
    run = _get_run(run_id)
    if run["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"run not complete: {run['status']}")
    from demand_signal_os.leaderboard import fit_winner_bundle

    result = run["result"]
    actuals = _build_actuals(run["request"])
    config = _build_config(run["request"])
    bundle = fit_winner_bundle(actuals, config, result.winner_method_id)
    return {
        "run_id": run_id,
        "winner_method_id": result.winner_method_id,
        "winner_is_benchmark": result.winner_is_benchmark,
        "bundle": bundle.model_dump(mode="json"),
    }


@router.get("/forecast/leaderboard/{run_id}/receipt")
async def get_receipt(run_id: str) -> dict[str, Any]:
    """Signed reproducibility receipt for the run (reuses the trust gate).

    The winner's empirical coverage + CRPS-vs-benchmark + benchmark-gate
    verdict are emitted as signed checks, certifying the leaderboard result
    is reproducible (content_hash) and trustworthy (beats naive).
    """
    run = _get_run(run_id)
    if run["status"] != "complete":
        raise HTTPException(status_code=409, detail=f"run not complete: {run['status']}")
    from trust_gate import dso_receipt

    result = run["result"]
    entries = {e.method_id: e for e in result.entries}
    winner = entries[result.winner_method_id]
    benchmark_crps = [e.crps for e in result.entries if e.is_benchmark]
    baseline_crps = min(benchmark_crps) if benchmark_crps else winner.crps

    checks = [
        {
            "name": "90% interval coverage",
            "measured_value": round(winner.coverage_90 or 0.0, 4),
            "reference_value": 0.90,
            "tolerance": 0.15,
            "direction": "match",
            "formula": "mean(1[actual in [q05,q95]])",
        },
        {
            "name": "CRPS vs best benchmark (ratio, <1 = beats naive)",
            "measured_value": round(winner.crps / baseline_crps, 4)
            if baseline_crps
            else 0.0,
            "reference_value": 1.0,
            "tolerance": 0.0,
            "direction": "lower_better",
            "formula": "winner_crps / best_benchmark_crps",
        },
        {
            "name": "beats all benchmarks (gate)",
            "measured_value": 1.0 if winner.beats_all_benchmarks else 0.0,
            "reference_value": 1.0,
            "tolerance": 0.0,
            "direction": "match",
            "formula": "all(winner_crps < benchmark_crps)",
        },
    ]
    caveats = (
        f"Leaderboard winner={result.winner_method_id} "
        f"(is_benchmark={result.winner_is_benchmark}); "
        f"{result.n_methods} methods over {winner.n_windows} windows; "
        f"reproducibility content_hash={result.content_hash}.",
    )
    r = dso_receipt(
        sku_id=result.config.sku_id,
        location_id=result.config.location_id,
        horizon_label=result.config.horizon_label,
        baseline_crps=baseline_crps,
        actual_count=winner.n_windows * result.config.horizon,
        checks=checks,
        caveats=caveats,
        # Deterministic receipt (RULE 5): derive produced_at from the injected
        # data cut so the same run yields a byte-identical signed receipt.
        produced_at=result.config.data_cut_timestamp,
    )
    payload: dict[str, Any] = r.model_dump(mode="json")
    return payload
