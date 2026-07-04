"""Inventory-policy route (**Wire W4 out** — DSO -> O2C per-SKU policy).

Given a `ForecastBundle` + policy config, returns a typed `InventoryPolicy` + `PIR`.
This is the sanctioned v0.1.5 REST extraction of the `o2c_adapter` (DSO CONSTITUTION
§11 / line 145: "inventory policies ... REST endpoint v0.1.5+").

Plan2Cash (Pattern G) calls this, projects the policy into O2C's per-SKU reorder config,
and pushes it to O2C. **DSO owns the policy math** (BOUNDARY §2); this endpoint never
actuates O2C directly — Plan2Cash is the sole cross-engine actuator.

Determinism (RULE 5): the policy is a pure function of the posted bundle + config; no
wall clock, no RNG. Gated by `require_api_key` (dev-open when `DSO_API_KEYS` is unset).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from demand_signal_os.api.auth import require_dso_access
from demand_signal_os.ops_schemas import ForecastBundle

router = APIRouter(tags=["inventory"])


class InventoryPolicyRequest(BaseModel):
    """A forecast + policy config -> one typed InventoryPolicy + PIR."""

    bundle: ForecastBundle
    lead_time_periods: float = Field(gt=0, description="lead time in bucket units")
    service_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    service_level_type: Literal["csl", "fill_rate"] = "csl"
    policy_type: Literal["qr", "ss"] = "qr"
    order_quantity: float | None = Field(default=None, gt=0, description="Q for (Q,R); derived if omitted")
    review_period_periods: float = Field(default=1.0, gt=0, description="review cadence for (s,S)")
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    carry_quantiles: bool = False


@router.post("/inventory/policy", dependencies=[Depends(require_dso_access)])
async def inventory_policy(body: InventoryPolicyRequest) -> dict[str, Any]:
    """Assemble a typed `InventoryPolicy` + `PIR` from a `ForecastBundle`.

    Returns 422 (not 500) on invalid policy inputs so the caller gets a clear reason.
    """
    # Lazy import: o2c_adapter -> qr/ss -> safety_stock pulls scipy; keep module import light.
    from demand_signal_os.consumers.o2c_adapter import build_inventory_policy, build_pir

    try:
        policy = build_inventory_policy(
            body.bundle,
            lead_time_periods=body.lead_time_periods,
            service_level=body.service_level,
            service_level_type=body.service_level_type,
            policy_type=body.policy_type,
            order_quantity=body.order_quantity,
            review_period_periods=body.review_period_periods,
            valid_from=body.valid_from,
            valid_until=body.valid_until,
        )
        pir = build_pir(body.bundle, carry_quantiles=body.carry_quantiles)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — surface a clean 422, not a 500
        raise HTTPException(
            status_code=422,
            detail=f"inventory policy failed: {type(exc).__name__}: {exc}",
        ) from exc

    return {
        "policy": policy.model_dump(mode="json"),
        "pir": pir.model_dump(mode="json"),
    }
