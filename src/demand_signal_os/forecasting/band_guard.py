"""Minimum-band-width guard for probabilistic forecasts.

Resolves the D5 UAT-1b finding (2026-06-08): on near-noiseless input,
methods like ETS correctly infer zero innovation variance and the
emitted quantile band collapses (q95 − q05 ≈ 0). Statistically right
but breaks downstream consumers — safety_stock collapses to 0, the
critic loses drift_magnitude signal, (Q,R) reorder drops the protection
buffer.

When a forecasting method's ``min_quantile_spread`` config is set, the
emitted Quantiles are passed through ``apply_min_band_floor`` which
expands the band symmetrically around q50 until ``q95 − q05`` meets
the floor. q50 (central tendency) is preserved exactly.

Standard regularization practice in IBP vendor implementations.
"""

from __future__ import annotations

from demand_signal_os.ops_schemas import Quantiles

# Default z-score weights (Gaussian-normalized) for the 7 canonical
# quantile levels — used when the input band is fully collapsed
# (current_spread <= 0). Anchored at z(0.95) = 1.6449 so q05/q95 land
# at ±half_spread and the intermediate quantiles interpolate the
# standard normal CDF.
_GAUSSIAN_Z = {
    "q05": -1.6449,
    "q10": -1.2816,
    "q25": -0.6745,
    "q50": 0.0,
    "q75": 0.6745,
    "q90": 1.2816,
    "q95": 1.6449,
}


def apply_min_band_floor(q: Quantiles, min_spread: float) -> Quantiles:
    """Enforce a minimum width on the quantile band (q95 − q05 >= min_spread).

    Behaviour:
    - ``min_spread <= 0`` → return ``q`` unchanged (guard off).
    - ``q95 − q05 >= min_spread`` → return ``q`` unchanged (band already wide).
    - ``q95 − q05 > 0`` but < min_spread → scale all quantiles relative to
      q50 so the new band exactly meets ``min_spread``. Preserves the
      shape (skewness, tail asymmetry).
    - ``q95 − q05 <= 0`` (fully degenerate) → distribute the 7 quantiles
      symmetrically around q50 using Gaussian z-scores normalized to
      reach ``±min_spread/2`` at q05/q95.

    In every case, q50 is preserved exactly and monotonicity is maintained.
    """
    if min_spread <= 0:
        return q

    current_spread = q.q95 - q.q05
    if current_spread >= min_spread:
        return q

    if current_spread <= 0:
        # Fully degenerate band — distribute symmetrically around q50.
        half = min_spread / 2.0
        return Quantiles(
            q05=q.q50 + _GAUSSIAN_Z["q05"] / _GAUSSIAN_Z["q95"] * half,
            q10=q.q50 + _GAUSSIAN_Z["q10"] / _GAUSSIAN_Z["q95"] * half,
            q25=q.q50 + _GAUSSIAN_Z["q25"] / _GAUSSIAN_Z["q95"] * half,
            q50=q.q50,
            q75=q.q50 + _GAUSSIAN_Z["q75"] / _GAUSSIAN_Z["q95"] * half,
            q90=q.q50 + _GAUSSIAN_Z["q90"] / _GAUSSIAN_Z["q95"] * half,
            q95=q.q50 + half,
        )

    scale = min_spread / current_spread
    return Quantiles(
        q05=q.q50 + scale * (q.q05 - q.q50),
        q10=q.q50 + scale * (q.q10 - q.q50),
        q25=q.q50 + scale * (q.q25 - q.q50),
        q50=q.q50,
        q75=q.q50 + scale * (q.q75 - q.q50),
        q90=q.q50 + scale * (q.q90 - q.q50),
        q95=q.q50 + scale * (q.q95 - q.q50),
    )
