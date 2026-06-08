"""Backtest metrics per BACKTESTING.md §4-§5.

References:
- CRPS: Gneiting & Raftery (2007), *JASA* 102(477)
- WIS: Bracher, Ray, Gneiting & Reich (2021), *PLOS Computational Biology* 17(2)
- WRMSSE: Makridakis, Spiliotis & Assimakopoulos (2022), *IJF* 38(4)
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from demand_signal_os.ops_schemas import Quantiles


def smape(actual: float, forecast: float) -> float | None:
    """Symmetric MAPE for a single observation. Returns None if undefined."""
    denom = abs(actual) + abs(forecast)
    if denom == 0:
        return None
    return float(2.0 * abs(actual - forecast) / denom)


def pinball_loss(actual: float, quantile_value: float, alpha: float) -> float:
    """Pinball (quantile) loss at level alpha in (0, 1)."""
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    diff = actual - quantile_value
    return float(max(alpha * diff, (alpha - 1.0) * diff))


def crps(actual: float, samples: Sequence[float]) -> float:
    """Empirical CRPS from a sample array — Gneiting-Raftery 2007.

    Per the standard estimator:
        CRPS(F, y) ≈ mean(|X - y|) - 0.5 * mean(|X - X'|)
    where X, X' are independent samples from F.
    """
    s = np.asarray(samples, dtype=float)
    if s.size == 0:
        raise ValueError("samples is empty")
    term1 = float(np.mean(np.abs(s - actual)))
    # Vectorized mean(|X - X'|) over the sample
    diffs = np.abs(s[:, None] - s[None, :])
    term2 = float(np.mean(diffs))
    return term1 - 0.5 * term2


def wis(actual: float, quantiles: Quantiles) -> float:
    """Weighted Interval Score per Bracher et al. 2021.

    Uses the 7 canonical quantile levels mapped to 3 prediction intervals:
    - alpha=0.10 → (q05, q95)
    - alpha=0.50 → (q25, q75)
    - alpha=0.80 → (q10, q90) — using these levels' centers gives 80% PI
    Median = q50.

    Returns the standard WIS value (lower is better).
    """
    median = quantiles.q50
    # (alpha, lower, upper) triplets
    intervals: list[tuple[float, float, float]] = [
        (0.10, quantiles.q05, quantiles.q95),
        (0.20, quantiles.q10, quantiles.q90),
        (0.50, quantiles.q25, quantiles.q75),
    ]
    K = len(intervals)
    total = 0.5 * abs(actual - median)
    for alpha, lower, upper in intervals:
        spread = upper - lower
        below = (2.0 / alpha) * max(lower - actual, 0.0)
        above = (2.0 / alpha) * max(actual - upper, 0.0)
        total += (alpha / 2.0) * (spread + below + above)
    return float(total / (K + 0.5))
