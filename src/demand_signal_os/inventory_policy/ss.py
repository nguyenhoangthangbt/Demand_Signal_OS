"""(s,S) periodic-review policy — per-echelon independent safety stock (R-7).

Reference: Zipkin (2000) ch. 9-10.

Per F2S_BOUNDARY R-7: per-echelon (s,S) with independent safety stock is
IN v0.1 (no network-topology config needed). Joint Graves-Willems optimal
multi-echelon allocation is OUT to v0.2.

s = reorder threshold (when inventory <= s, order up to S)
S = order-up-to level
"""

from __future__ import annotations

from demand_signal_os.ops_schemas import Quantiles
from demand_signal_os.inventory_policy.safety_stock import (
    safety_stock_csl,
    safety_stock_fill_rate,
)


def ss_policy(
    forecast_q: Quantiles,
    forecast_mean: float,
    lead_time_periods: float,
    review_period_periods: float,
    service_level: float,
    service_level_type: str,
    Q_for_fill_rate: float = 1.0,
) -> tuple[float, float, float]:
    """Compute (s, S, safety_stock) for a (s,S) policy.

    Per Zipkin ch. 9-10: the protection window is (lead_time + review_period)
    instead of just lead_time, because between reviews the system is exposed.
    """
    protection_periods = lead_time_periods + review_period_periods

    if service_level_type == "csl":
        ss = safety_stock_csl(forecast_q, protection_periods, service_level)
    elif service_level_type == "fill_rate":
        ss = safety_stock_fill_rate(
            forecast_q, protection_periods, service_level, Q_for_fill_rate
        )
    else:
        raise ValueError(f"unknown service_level_type: {service_level_type}")

    expected_demand_during_protection = forecast_mean * protection_periods
    s = expected_demand_during_protection + ss
    # Order-up-to: cover one review period of expected demand above s.
    S = s + forecast_mean * review_period_periods
    return s, S, ss
