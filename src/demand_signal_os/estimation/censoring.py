"""Three-tier censoring adapter per CONTRACTS §2.1.

References:
- Nahmias (1994), *Naval Research Logistics* 41(6)
- Huh & Rusmevichientong (2009), *Math. Operations Research* 34(1)
- Sachs & Minner (2014), *International Journal of Production Economics* 149

v0.1 implements Tier 1 only (heuristic at ingestion). Tiers 2-3 require
upstream O2C schema changes — see CONTRACTS §2.1.
"""

from __future__ import annotations

from dataclasses import dataclass

from demand_signal_os.ops_schemas import CensoringFlag, DemandActual


@dataclass
class InventorySnapshot:
    """Per-(SKU, location) inventory position at a point in time."""

    sku_id: str
    location_id: str
    in_stock_at_bucket_start: bool
    stockout_hours_in_bucket: float = 0.0


def tier1_heuristic(
    record: DemandActual,
    snapshot: InventorySnapshot | None,
) -> DemandActual:
    """Tier 1 heuristic — resolves CensoringFlag.UNKNOWN at ingestion.

    Rules:
    - units_sold > 0 → OBSERVED (real demand directly seen, no censoring)
    - units_sold == 0 + in_stock + snapshot available → REAL_ZERO
    - units_sold == 0 + out_of_stock + snapshot available → STOCKOUT_CENSORED
    - units_sold == 0 + no snapshot → UNKNOWN (exclude from training)
    - Pre-set flag (not UNKNOWN) → respected
    """
    if record.censoring != CensoringFlag.UNKNOWN:
        return record

    if record.units_sold > 0:
        return record.model_copy(update={"censoring": CensoringFlag.OBSERVED})

    if snapshot is None:
        return record  # no info, stay UNKNOWN — caller excludes

    if snapshot.in_stock_at_bucket_start:
        return record.model_copy(update={"censoring": CensoringFlag.REAL_ZERO})
    else:
        return record.model_copy(
            update={
                "censoring": CensoringFlag.STOCKOUT_CENSORED,
                "stockout_duration_hours": snapshot.stockout_hours_in_bucket or None,
            }
        )


def usable_for_training(record: DemandActual) -> bool:
    """Records with UNKNOWN censoring are excluded from training."""
    return record.censoring != CensoringFlag.UNKNOWN
