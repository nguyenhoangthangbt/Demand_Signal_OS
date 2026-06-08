"""Newsvendor policy — single-period perishable.

Reference: Zipkin (2000) ch. 9; Silver-Pyke-Peterson (1998) ch. 9.

Critical ratio CR = c_u / (c_u + c_o)  where c_u = underage cost (lost sale),
c_o = overage cost (holding). Optimal q* = F^-1(CR).
"""

from __future__ import annotations

from demand_signal_os.ops_schemas import Quantiles


def newsvendor_quantity(forecast_q: Quantiles, critical_ratio: float) -> float:
    """Optimal newsvendor quantity at the given critical ratio.

    Quantile interpolation across the 7 canonical quantiles.
    """
    if not 0.0 < critical_ratio < 1.0:
        raise ValueError("critical_ratio must be in (0, 1)")

    levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    values = [
        forecast_q.q05, forecast_q.q10, forecast_q.q25, forecast_q.q50,
        forecast_q.q75, forecast_q.q90, forecast_q.q95,
    ]

    if critical_ratio <= levels[0]:
        return float(values[0])
    if critical_ratio >= levels[-1]:
        return float(values[-1])

    for i in range(len(levels) - 1):
        if levels[i] <= critical_ratio <= levels[i + 1]:
            t = (critical_ratio - levels[i]) / (levels[i + 1] - levels[i])
            return float(values[i] + t * (values[i + 1] - values[i]))

    return float(forecast_q.q50)  # unreachable; fallback
