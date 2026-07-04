"""Demand-actuals ingestion route (**Wire W8 in** — O2C -> DSO via Plan2Cash Pattern F).

Accepts realized demand observations (shaped by O2C, forwarded by Plan2Cash Pattern F),
runs the DSO-sovereign three-tier censoring classifier
(`estimation.censoring.tier1_heuristic`) to resolve each observation's `CensoringFlag`,
and — when a matching `ForecastBundle` is supplied — scores the forecast against the real
actual via `accuracy.evaluate`, so `drift_magnitude` is computed on REAL censored actuals
instead of the synthetic `UNKNOWN` points the forecast preview reconstructs today.

Boundary: **censoring math is DSO's** (BOUNDARY §5); O2C supplies the raw observation +
inventory snapshot; Plan2Cash is a dumb forwarder (the bus). DSO has no DB (library-first,
D1), so this endpoint is **stateless**: classify + score + return. Durable actuals
persistence for the Loop-δ `baseline_crps` refresh is deferred to Phase F.3.

Determinism (RULE 5): classification + scoring are pure functions of the input; the
endpoint reads no wall clock (`recorded_at` comes from the caller's observation).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from demand_signal_os.api.auth import require_api_key
from demand_signal_os.ops_schemas import CensoringFlag, DemandActual, ForecastBundle

router = APIRouter(tags=["actuals"])

_MAX_OBSERVATIONS = 5000  # bound per-call compute


class InventorySnapshotIn(BaseModel):
    """The O2C-supplied inventory position DSO's classifier needs."""

    in_stock_at_bucket_start: bool
    stockout_hours_in_bucket: float = Field(default=0.0, ge=0.0)


class ActualObservation(BaseModel):
    """One realized demand observation + its optional inventory snapshot.

    `actual.censoring` is typically `UNKNOWN` on the wire — the classifier resolves it.
    """

    actual: DemandActual
    snapshot: InventorySnapshotIn | None = None


class ActualsIngestRequest(BaseModel):
    observations: list[ActualObservation] = Field(min_length=1, max_length=_MAX_OBSERVATIONS)
    bundle: ForecastBundle | None = None
    baseline_crps: float | None = Field(default=None, gt=0)


@router.post("/actuals", dependencies=[Depends(require_api_key)])
async def ingest_actuals(body: ActualsIngestRequest) -> dict[str, Any]:
    """Classify censoring on each actual and (optionally) score the matching forecast."""
    from demand_signal_os.estimation.censoring import (
        InventorySnapshot,
        tier1_heuristic,
        usable_for_training,
    )

    classified: list[DemandActual] = []
    tier_counts: dict[str, int] = {flag.value: 0 for flag in CensoringFlag}

    for obs in body.observations:
        snapshot = None
        if obs.snapshot is not None:
            snapshot = InventorySnapshot(
                sku_id=obs.actual.sku_id,
                location_id=obs.actual.location_id,
                in_stock_at_bucket_start=obs.snapshot.in_stock_at_bucket_start,
                stockout_hours_in_bucket=obs.snapshot.stockout_hours_in_bucket,
            )
        resolved = tier1_heuristic(obs.actual, snapshot)
        classified.append(resolved)
        tier_counts[resolved.censoring.value] += 1

    usable = [r for r in classified if usable_for_training(r)]

    accuracy: dict[str, Any] | None = None
    if body.bundle is not None:
        bundle = body.bundle
        match = next(
            (
                r
                for r in classified
                if r.sku_id == bundle.sku_id
                and r.location_id == bundle.location_id
                and r.bucket == bundle.bucket
            ),
            None,
        )
        if match is not None:
            from demand_signal_os.accuracy import evaluate

            try:
                acc = evaluate(bundle, match, baseline_crps=body.baseline_crps)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail=f"accuracy scoring failed: {exc}"
                ) from exc
            accuracy = acc.model_dump(mode="json")

    return {
        "classified": [r.model_dump(mode="json") for r in classified],
        "tier_counts": {k: v for k, v in tier_counts.items() if v},
        "usable_count": len(usable),
        "accuracy": accuracy,
    }
