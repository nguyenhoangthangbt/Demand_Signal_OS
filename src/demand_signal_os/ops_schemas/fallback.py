"""ForecastFallbackStrategy primitive per CONTRACTS §8.

The biggest blind spot surfaced in Round-1 brainstorming. The contract
MUST exist before engine code, even if most algorithms ship in v0.1.5.
v0.1 implements only the `reject` strategy.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ForecastFallbackStrategy(BaseModel):
    schema_version: int = 1
    strategy_type: Literal[
        "cold_start",
        "promo_uplift",
        "discontinued",
        "insufficient_history",
        "new_location",
    ]
    fallback: Literal[
        "family_aggregate_prior",
        "location_aggregate_prior",
        "expert_judgment_override",
        "empirical_only",
        "reject",
    ]
    config: dict = {}
