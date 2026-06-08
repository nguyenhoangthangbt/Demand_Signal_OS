"""(Q,R) continuous-review policy.

Reference: Silver-Pyke-Peterson (1998) ch. 7.

Q = order quantity (typically EOQ-derived)
R = reorder point = E[D_LTD] + safety_stock
"""

from __future__ import annotations

import math

from demand_signal_os.inventory_policy.safety_stock import (
    safety_stock_csl,
    safety_stock_fill_rate,
)
from demand_signal_os.ops_schemas import Quantiles


def eoq(annual_demand: float, order_cost: float, holding_cost_per_unit: float) -> float:
    """Economic Order Quantity per Harris (1913); Silver-Pyke-Peterson ch. 5."""
    if annual_demand <= 0 or order_cost <= 0 or holding_cost_per_unit <= 0:
        raise ValueError("all EOQ inputs must be positive")
    return float(math.sqrt(2.0 * annual_demand * order_cost / holding_cost_per_unit))


def qr_policy(
    forecast_q: Quantiles,
    forecast_mean: float,
    lead_time_periods: float,
    service_level: float,
    service_level_type: str,
    Q: float,
) -> tuple[float, float, float]:
    """Compute (Q, R, safety_stock) for a (Q,R) policy.

    Returns (Q_in, R, SS).
    """
    if service_level_type == "csl":
        ss = safety_stock_csl(forecast_q, lead_time_periods, service_level)
    elif service_level_type == "fill_rate":
        ss = safety_stock_fill_rate(forecast_q, lead_time_periods, service_level, Q)
    else:
        raise ValueError(f"unknown service_level_type: {service_level_type}")

    expected_demand_during_lt = forecast_mean * lead_time_periods
    R = expected_demand_during_lt + ss
    return Q, R, ss
