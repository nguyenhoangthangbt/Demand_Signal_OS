"""Base-stock policy — single-echelon lost-sales / backorder.

Reference: Zipkin (2000) ch. 6.

Base-stock level S* satisfies P(D_LTD <= S*) = critical_ratio for backorder,
or quantile newsvendor solution for lost-sales.
"""

from __future__ import annotations

from demand_signal_os.inventory_policy.newsvendor import newsvendor_quantity
from demand_signal_os.ops_schemas import Quantiles


def base_stock_level(forecast_q: Quantiles, critical_ratio: float) -> float:
    """Base-stock optimal level at critical ratio.

    Reuses newsvendor quantile interpolation — the formulation is identical
    for the single-period case.
    """
    return newsvendor_quantity(forecast_q, critical_ratio)
