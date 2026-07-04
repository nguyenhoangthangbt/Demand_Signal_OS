"""O2C consumer adapter — assemble a typed InventoryPolicy + PIR from a ForecastBundle.

Producer-side adapter for **Wire W4** (DSO -> O2C per-SKU inventory policy), per
`Plan2Cash_os/docs/CONTRACTS.md §3` + `BOUNDARY.md §2` (inventory-policy math is
DSO-sovereign; O2C *consumes* `InventoryPolicy`/`PIR` and never invents policy math).

The `inventory_policy` kernels (`qr_policy`, `ss_policy`, `safety_stock_*`) return raw
`(Q, R, ss)` / `(s, S, ss)` floats. This module is the missing **envelope-assembly**
layer: it wraps those kernel outputs into the `ops_schemas.InventoryPolicy` contract
(discriminated `parameters` + `reorder_triggers` + `forecast_provenance` + validity
window) that Plan2Cash projects and pushes to O2C via Pattern G. It reuses the sovereign
kernels verbatim — it does NOT reimplement any policy math.

Determinism (RULE 5): a pure function of `(bundle, config)` — no wall clock, no RNG.
The validity window derives from the bundle's `bucket`, never `datetime.now()`, so the
same bundle + config yields a byte-identical policy.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Literal

from demand_signal_os.inventory_policy.pir import pir_from_forecast
from demand_signal_os.inventory_policy.qr import qr_policy
from demand_signal_os.inventory_policy.ss import ss_policy
from demand_signal_os.ops_schemas import (
    PIR,
    ForecastBundle,
    InventoryPolicy,
    QRParameters,
    ReorderTrigger,
    SSParameters,
)

PolicyType = Literal["qr", "ss"]
ServiceLevelType = Literal["csl", "fill_rate"]


def _bucket_datetime(d: date) -> datetime:
    """Project a bucket boundary date to a deterministic UTC datetime."""
    return datetime.combine(d, time.min, tzinfo=UTC)


def build_inventory_policy(
    bundle: ForecastBundle,
    *,
    lead_time_periods: float,
    service_level: float = 0.95,
    service_level_type: ServiceLevelType = "csl",
    policy_type: PolicyType = "qr",
    order_quantity: float | None = None,
    review_period_periods: float = 1.0,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
) -> InventoryPolicy:
    """Assemble a typed `InventoryPolicy` from a `ForecastBundle` + policy config.

    Parameters
    ----------
    bundle
        The forecast the policy is derived from. Supplies identity
        (`sku_id`/`location_id`), the quantile band (drives safety stock), the
        mean (drives expected lead-time demand), and the provenance chain.
    lead_time_periods
        Replenishment lead time in the bundle's bucket units (e.g. days). > 0.
    service_level / service_level_type
        Target cycle-service-level (`csl`) or unit-fill-rate (`fill_rate`).
    policy_type
        `"qr"` (continuous review, reorder point `R`) or `"ss"` (periodic
        review, reorder threshold `s` + order-up-to `S`).
    order_quantity
        `Q` for a (Q,R) policy. When omitted, defaults to a lead-time's worth of
        expected demand (`mean * lead_time_periods`, floored at 1.0) so the
        result is deterministic without an EOQ cost model. Ignored for `ss`
        except as the fill-rate `Q`.
    review_period_periods
        Review cadence for `ss` (periods between reviews). Ignored for `qr`.
    valid_from / valid_until
        Validity window. Default to the bundle's bucket start/end (deterministic).

    Returns
    -------
    InventoryPolicy
        The contract O2C's reorder-execution consumer reads: per-SKU/location
        `R` (or `s`/`S`), safety stock, a `below_reorder_point` trigger, and the
        forecast provenance chaining back to the bundle that produced it.
    """
    if lead_time_periods <= 0:
        raise ValueError("lead_time_periods must be positive")

    vfrom = valid_from if valid_from is not None else _bucket_datetime(bundle.bucket.start)
    vuntil = valid_until if valid_until is not None else _bucket_datetime(bundle.bucket.end)

    if policy_type == "qr":
        q_in = (
            order_quantity
            if order_quantity is not None
            else max(bundle.mean * lead_time_periods, 1.0)
        )
        q_out, reorder_point, ss = qr_policy(
            forecast_q=bundle.quantiles,
            forecast_mean=bundle.mean,
            lead_time_periods=lead_time_periods,
            service_level=service_level,
            service_level_type=service_level_type,
            Q=q_in,
        )
        parameters = QRParameters(Q=q_out, R=reorder_point)
        threshold = reorder_point
    elif policy_type == "ss":
        s, big_s, ss = ss_policy(
            forecast_q=bundle.quantiles,
            forecast_mean=bundle.mean,
            lead_time_periods=lead_time_periods,
            review_period_periods=review_period_periods,
            service_level=service_level,
            service_level_type=service_level_type,
            Q_for_fill_rate=order_quantity if order_quantity is not None else 1.0,
        )
        parameters = SSParameters(s=s, S=big_s)
        threshold = s
    else:  # pragma: no cover — Literal guards this at the type layer
        raise ValueError(f"unknown policy_type: {policy_type!r}")

    trigger = ReorderTrigger(
        trigger_type="below_reorder_point",
        sku_id=bundle.sku_id,
        location_id=bundle.location_id,
        threshold=threshold,
    )

    return InventoryPolicy(
        sku_id=bundle.sku_id,
        location_id=bundle.location_id,
        parameters=parameters,
        safety_stock=ss,
        service_level_target=service_level,
        service_level_type=service_level_type,
        reorder_triggers=[trigger],
        forecast_provenance=bundle.provenance,
        valid_from=vfrom,
        valid_until=vuntil,
    )


def build_pir(bundle: ForecastBundle, *, carry_quantiles: bool = False) -> PIR:
    """`PIR` from the same bundle — thin re-export of the sovereign generator."""
    return pir_from_forecast(bundle, carry_quantiles=carry_quantiles)
