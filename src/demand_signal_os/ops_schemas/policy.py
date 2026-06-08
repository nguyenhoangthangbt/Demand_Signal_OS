"""Inventory policy + PIR types per CONTRACTS §1.4.

Discriminated union per `policy_type` (S8) — replaces the v0 `parameters: dict`
type-safety hole. service_level_type adds CSL vs fill-rate selection (U3).
PIR.quantiles is optional (D5/S7) — ERP consumers expect deterministic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from demand_signal_os.ops_schemas.forecast import ForecastProvenance, Quantiles
from demand_signal_os.ops_schemas.hierarchy import TimeBucket


class QRParameters(BaseModel):
    policy_type: Literal["qr"] = "qr"
    Q: float  # order quantity
    R: float  # reorder point


class SSParameters(BaseModel):
    policy_type: Literal["ss"] = "ss"
    s: float  # reorder threshold
    S: float  # order-up-to level
    echelon_index: int = 0  # per-echelon (s,S) - 0=leaf, N=highest


class BaseStockParameters(BaseModel):
    policy_type: Literal["base_stock"] = "base_stock"
    base_level: float


class NewsvendorParameters(BaseModel):
    policy_type: Literal["newsvendor"] = "newsvendor"
    optimal_quantity: float
    critical_ratio: float


PolicyParameters = Annotated[
    QRParameters | SSParameters | BaseStockParameters | NewsvendorParameters,
    Field(discriminator="policy_type"),
]


class ReorderTrigger(BaseModel):
    schema_version: int = 1
    trigger_type: Literal["below_reorder_point", "periodic_review", "manual"]
    sku_id: str
    location_id: str
    threshold: float | None = None
    review_cadence: str | None = None


class InventoryPolicy(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    parameters: PolicyParameters
    safety_stock: float
    service_level_target: float
    service_level_type: Literal["csl", "fill_rate"] = "csl"
    reorder_triggers: list[ReorderTrigger]
    forecast_provenance: ForecastProvenance
    valid_from: datetime
    valid_until: datetime


class PIR(BaseModel):
    """Planned Independent Requirement — PlanningOS + O2C consumers only (S7).

    SimOS does NOT consume PIRs (samples from ForecastBundle.distribution).
    """

    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    quantity_planned: float
    quantiles: Quantiles | None = None
    forecast_provenance: ForecastProvenance
