"""Safety stock math tests — both CSL and fill-rate modes."""

from __future__ import annotations

import math

from demand_signal_os.inventory_policy.safety_stock import (
    lead_time_demand_std,
    safety_stock_csl,
    safety_stock_fill_rate,
)
from demand_signal_os.ops_schemas import Quantiles


def _q() -> Quantiles:
    # Symmetric Gaussian-shaped quantiles around 10 with sigma=3.
    return Quantiles(
        q05=10 - 1.6449 * 3,
        q10=10 - 1.2816 * 3,
        q25=10 - 0.6745 * 3,
        q50=10.0,
        q75=10 + 0.6745 * 3,
        q90=10 + 1.2816 * 3,
        q95=10 + 1.6449 * 3,
    )


def test_lead_time_demand_std_scales_with_sqrt_lead_time() -> None:
    """sigma_LTD should scale with sqrt(L) per Silver-Pyke-Peterson §7."""
    s1 = lead_time_demand_std(_q(), 1.0)
    s4 = lead_time_demand_std(_q(), 4.0)
    # s4 should be ~2x s1 (since sqrt(4)=2)
    assert math.isclose(s4 / s1, 2.0, rel_tol=0.05)


def test_safety_stock_csl_at_95_percent() -> None:
    """SS at 95% CSL = 1.6449 * sigma_LTD per standard normal table."""
    ss = safety_stock_csl(_q(), lead_time_periods=1.0, service_level_alpha=0.95)
    # With sigma=3 per period, lead=1, expected SS ≈ 1.6449 * 3 ≈ 4.93
    assert math.isclose(ss, 1.6449 * 3, rel_tol=0.05)


def test_safety_stock_csl_at_99_percent_is_higher_than_95() -> None:
    ss_95 = safety_stock_csl(_q(), 1.0, 0.95)
    ss_99 = safety_stock_csl(_q(), 1.0, 0.99)
    assert ss_99 > ss_95


def test_safety_stock_fill_rate_in_zero_one() -> None:
    ss = safety_stock_fill_rate(_q(), lead_time_periods=1.0, fill_rate_target=0.98, Q=50.0)
    assert ss > 0  # any non-100% fill rate over a positive variance distribution
    assert ss < 100  # sanity bound


def test_safety_stock_fill_rate_higher_for_tighter_target() -> None:
    ss_95 = safety_stock_fill_rate(_q(), 1.0, 0.95, Q=50.0)
    ss_99 = safety_stock_fill_rate(_q(), 1.0, 0.99, Q=50.0)
    assert ss_99 > ss_95
