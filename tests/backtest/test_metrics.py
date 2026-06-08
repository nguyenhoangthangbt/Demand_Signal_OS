"""Metric correctness tests — pin reference values for CRPS, WIS, pinball, sMAPE."""

from __future__ import annotations

import math

import numpy as np

from demand_signal_os.backtest.metrics import crps, pinball_loss, smape, wis
from demand_signal_os.ops_schemas import Quantiles


def test_smape_zero_when_perfect() -> None:
    assert smape(10.0, 10.0) == 0.0


def test_smape_undefined_at_zero_zero() -> None:
    assert smape(0.0, 0.0) is None


def test_smape_symmetric_in_arguments() -> None:
    # sMAPE is symmetric in |a-f| / (|a| + |f|) — so swapping a, f gives the same value
    a = smape(10.0, 20.0)
    b = smape(20.0, 10.0)
    assert a is not None and b is not None
    assert math.isclose(a, b)


def test_pinball_loss_at_q50_is_half_abs_error() -> None:
    # At alpha=0.5, pinball = 0.5 * |actual - q|
    assert math.isclose(pinball_loss(10.0, 8.0, 0.5), 1.0)
    assert math.isclose(pinball_loss(8.0, 10.0, 0.5), 1.0)


def test_pinball_loss_asymmetric_at_q90() -> None:
    # At alpha=0.9, under-prediction is penalized 9x more than over-prediction
    under = pinball_loss(10.0, 8.0, 0.9)  # forecast under actual
    over = pinball_loss(8.0, 10.0, 0.9)   # forecast over actual
    assert under > over


def test_crps_zero_for_point_mass_at_actual() -> None:
    """CRPS of a deterministic forecast at the actual is 0."""
    samples = np.full(1000, 10.0)
    assert crps(10.0, samples) == 0.0


def test_crps_positive_for_off_target() -> None:
    samples = np.full(1000, 5.0)
    assert crps(10.0, samples) > 0.0


def test_wis_zero_for_perfect_calibration() -> None:
    """WIS = 0 when actual = median and all intervals collapse to median."""
    q = Quantiles(q05=10.0, q10=10.0, q25=10.0, q50=10.0,
                  q75=10.0, q90=10.0, q95=10.0)
    assert wis(10.0, q) == 0.0


def test_wis_increases_when_actual_outside_intervals() -> None:
    q = Quantiles(q05=5.0, q10=6.0, q25=8.0, q50=10.0,
                  q75=12.0, q90=14.0, q95=15.0)
    inside = wis(10.0, q)  # actual = median
    outside = wis(50.0, q)  # actual way above q95
    assert outside > inside
