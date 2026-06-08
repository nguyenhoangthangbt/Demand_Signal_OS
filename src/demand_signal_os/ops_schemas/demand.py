"""Demand signal + actual types per CONTRACTS §1.2.

CensoringFlag is the load-bearing field per the three-tier adapter strategy
(CONTRACTS §2.1). Zero sales is NEVER silently treated as zero demand.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from demand_signal_os.ops_schemas.hierarchy import TimeBucket


class CensoringFlag(str, Enum):
    """Status of a DemandActual's units_sold value.

    OBSERVED — units_sold > 0 with no stockout; the value is real demand.
    REAL_ZERO — units_sold == 0, in stock the whole bucket; genuine no-demand.
    STOCKOUT_CENSORED — units_sold == 0 because SKU was out of stock.
    PARTIAL_CENSORED — some demand observed before mid-bucket stockout.
    UNKNOWN — legacy / source did not flag; excluded from training.
    """

    OBSERVED = "observed"
    REAL_ZERO = "real_zero"
    STOCKOUT_CENSORED = "stockout_censored"
    PARTIAL_CENSORED = "partial_censored"
    UNKNOWN = "unknown"


class DemandActual(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    units_sold: float
    units_demanded: float | None = None
    censoring: CensoringFlag
    stockout_duration_hours: float | None = None
    source_system: str
    recorded_at: datetime


class DemandSignal(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    signal_type: Literal[
        "actual",
        "pos",
        "promo_flag",
        "weather",
        "calendar_event",
        "macro",
        "research_covariate",
    ]
    value: float | str | dict
    source_system: str
    provenance_id: str
