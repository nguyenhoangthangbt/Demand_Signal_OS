"""Safety stock — dual mode (CSL + fill-rate) per CONSTITUTION §6 + U3.

References:
- Silver, Pyke & Peterson (1998), *Inventory Management and Production
  Planning and Scheduling* (3rd ed.) ch. 7
- Zipkin (2000), *Foundations of Inventory Management*, ch. 6
"""

from __future__ import annotations

from scipy import stats

from demand_signal_os.ops_schemas import Quantiles


def lead_time_demand_std(forecast_q: Quantiles, lead_time_periods: float) -> float:
    """Approximate sigma_LTD from forecast quantiles.

    Uses the q90-q10 span as a Gaussian-equivalent 2.5632·sigma estimator
    per Hyndman-Athanasopoulos ch. 7.5.
    """
    sigma_per_period = (forecast_q.q90 - forecast_q.q10) / 2.5632
    sigma_per_period = max(sigma_per_period, 1e-9)
    return float(sigma_per_period * (lead_time_periods**0.5))


def safety_stock_csl(
    forecast_q: Quantiles,
    lead_time_periods: float,
    service_level_alpha: float,
) -> float:
    """Cycle-service-level (CSL) mode: SS = z_alpha · sigma_LTD.

    service_level_alpha is the target CSL in (0, 1), e.g. 0.95.
    Per Silver-Pyke-Peterson (1998) §7.
    """
    if not 0.0 < service_level_alpha < 1.0:
        raise ValueError("service_level_alpha must be in (0, 1)")
    sigma_ltd = lead_time_demand_std(forecast_q, lead_time_periods)
    z_alpha = float(stats.norm.ppf(service_level_alpha))
    return max(z_alpha * sigma_ltd, 0.0)


def safety_stock_fill_rate(
    forecast_q: Quantiles,
    lead_time_periods: float,
    fill_rate_target: float,
    Q: float,
) -> float:
    """Unit-fill-rate (UFR) mode: SS satisfying 1 - E[BO]/Q = fill_rate_target.

    Per Silver-Pyke-Peterson (1998) §7.4.2. Solved numerically via the
    expected-shortage function under Gaussian LTD.

    Q is the order quantity (from the (Q,R) policy).
    """
    if not 0.0 < fill_rate_target < 1.0:
        raise ValueError("fill_rate_target must be in (0, 1)")
    if Q <= 0:
        raise ValueError("Q must be positive")

    sigma_ltd = lead_time_demand_std(forecast_q, lead_time_periods)
    target_backorder = (1.0 - fill_rate_target) * Q

    # E[BO](k) = sigma_LTD * (phi(k) - k * (1 - Phi(k)))
    # Solve for k such that sigma_LTD * G(k) = target_backorder.
    # G(k) = phi(k) - k * (1 - Phi(k)) is monotone decreasing in k.
    g_target = target_backorder / sigma_ltd if sigma_ltd > 0 else 0.0

    def g(k: float) -> float:
        return float(stats.norm.pdf(k) - k * (1.0 - stats.norm.cdf(k)))

    # Bisection in [-3, 6] — covers ~99.7% of practical fill rates
    lo, hi = -3.0, 6.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if g(mid) > g_target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-6:
            break
    k_star = (lo + hi) / 2
    return max(k_star * sigma_ltd, 0.0)
