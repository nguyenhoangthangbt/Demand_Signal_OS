"""Identity + hierarchy types per CONTRACTS §1.1."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

ArchetypeTag = Literal[
    "discrete_mfg",
    "pharma",
    "fashion",
    "grocery_fmcg",
    "automotive_oem",
]


class SKU(BaseModel):
    schema_version: int = 1
    sku_id: str
    family_id: str | None = None
    category_id: str | None = None
    abc_class: Literal["A", "B", "C"]
    archetype: ArchetypeTag


class Location(BaseModel):
    schema_version: int = 1
    location_id: str
    location_type: Literal["factory", "central_dc", "regional_dc", "store", "vendor"]
    region_id: str | None = None
    parent_location_id: str | None = None


class TimeBucket(BaseModel):
    schema_version: int = 1
    period: Literal["day", "week", "month", "quarter"]
    start: date
    end: date
    timezone: str = "UTC"
