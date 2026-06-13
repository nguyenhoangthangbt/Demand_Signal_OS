"""Trust-gate receipt routes for DemandSignalOS (DECISIONS_LOG §P #65).

Mirrors the SimOS reference (``simulation_os/api/calibration_routes.py``):
emit a SIGNED ``CalibrationReceipt`` for a forecast run's checks and export the
self-auditable validation workbook. The engine signs with the demandsignal key
(test-mode secret until ``P2C_CAL_SECRET_DEMANDSIGNAL`` is provisioned). No tier
gating, no auth — this is a credibility / trust-building surface.

LIGHT by design: imports ``trust_gate`` + ``excel_io`` only inside the handlers,
never ``demand_signal_os``. The receipt is emitted from posted/example checks,
not by running a live forecast (so the heavy DSO stack is not needed here).
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["trust-gate"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ReceiptCheckIn(BaseModel):
    name: str
    measured_value: float
    reference_value: float | None = None
    tolerance: float = 0.0
    tolerance_kind: str = "absolute"
    direction: str = "match"
    gate: str = "hard"
    formula: str | None = None


class ReceiptRequest(BaseModel):
    sku_id: str
    location_id: str
    horizon_label: str = "operational"
    baseline_crps: float = Field(gt=0)
    actual_count: int = Field(gt=0)
    checks: list[ReceiptCheckIn] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    upstream_receipt_refs: list[str] = Field(default_factory=list)


# A real, realistic DSO forecast-trust example (operational H+4w run on
# SKU-4471 @ DC-EAST): 90% interval coverage, CRPS-vs-baseline ratio, drift.
_EXAMPLE_CHECKS = [
    {
        "name": "90% interval coverage",
        "measured_value": 0.91,
        "reference_value": 0.90,
        "tolerance": 0.05,
        "direction": "match",
        "formula": "mean(1[actual in [q05,q95]])",
    },
    {
        "name": "CRPS vs baseline (ratio)",
        "measured_value": 0.86,
        "reference_value": 1.0,
        "tolerance": 0.5,
        "direction": "lower_better",
        "formula": "crps_model / baseline_crps",
    },
    {
        "name": "drift magnitude (<1.5 = stable)",
        "measured_value": 0.86,
        "reference_value": 1.5,
        "tolerance": 0.1,
        "direction": "lower_better",
        "formula": "crps / baseline_crps",
    },
]
_EXAMPLE_CAVEATS = (
    "Operational horizon H+4w; ETS forecast scored on 28 observed days; "
    "CRPS per Gneiting-Raftery 2007.",
)


# ---------------------------------------------------------------------------
# POST /calibration/receipt — emit a SIGNED receipt for posted checks
# ---------------------------------------------------------------------------


@router.post("/calibration/receipt")
async def emit_receipt(body: ReceiptRequest) -> dict:
    """Emit a SIGNED trust receipt for a forecast run's checks."""
    from trust_gate import dso_receipt

    r = dso_receipt(
        sku_id=body.sku_id,
        location_id=body.location_id,
        horizon_label=body.horizon_label,
        baseline_crps=body.baseline_crps,
        actual_count=body.actual_count,
        checks=[c.model_dump() for c in body.checks],
        caveats=tuple(body.caveats),
        upstream_receipt_refs=tuple(body.upstream_receipt_refs),
    )
    return r.model_dump(mode="json")


# ---------------------------------------------------------------------------
# GET /calibration/receipt/example — a real signed example for the Verify UI
# ---------------------------------------------------------------------------


@router.get("/calibration/receipt/example")
async def example_receipt() -> dict:
    """A real signed example receipt (SKU-4471 @ DC-EAST) for the Verify UI default."""
    from trust_gate import dso_receipt

    r = dso_receipt(
        sku_id="SKU-4471",
        location_id="DC-EAST",
        horizon_label="operational",
        baseline_crps=12.4,
        actual_count=28,
        checks=_EXAMPLE_CHECKS,
        caveats=_EXAMPLE_CAVEATS,
    )
    return r.model_dump(mode="json")


# ---------------------------------------------------------------------------
# POST /calibration/receipt/xlsx — export the self-auditable workbook
# ---------------------------------------------------------------------------


@router.post("/calibration/receipt/xlsx")
async def receipt_xlsx(receipt: dict = Body(...)) -> StreamingResponse:
    """Export a receipt as the self-auditable validation workbook (.xlsx)."""
    from excel_io.verify_export import receipt_to_validation_xlsx

    prov = receipt.get("provenance") or {}
    receipt.setdefault("engine", prov.get("engine", "demandsignal"))
    xlsx = receipt_to_validation_xlsx(receipt)
    return StreamingResponse(
        io.BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=validation.xlsx"},
    )
