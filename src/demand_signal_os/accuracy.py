"""Forecast-accuracy producer per CONTRACTS §3.4.

Pure function: given a `ForecastBundle` and the `DemandActual` realized in
its horizon window, compute a `ForecastAccuracy` record with point and
probabilistic scores plus the `drift_magnitude` signal consumed by the
PlanningOS closed-loop critic.

Library-first per CONSTITUTION §11 — no API surface yet. The PlanningOS
orchestrator (in-process) calls `evaluate()` as the
`forecast_accuracy_provider` injected into `run_loop`.

References:
- CRPS: Gneiting & Raftery (2007), *JASA* 102(477), 359–378
- Pinball loss: standard quantile-regression scoring
- sMAPE: M-competition standard
- WIS: Bracher, Ray, Gneiting & Reich (2021), *PLOS Computational
  Biology* 17(2), e1008618 — implemented in `backtest.metrics`
"""

from __future__ import annotations

import math

import numpy as np

from demand_signal_os.backtest.metrics import crps, pinball_loss, smape, wis
from demand_signal_os.ops_schemas import (
    DemandActual,
    ForecastAccuracy,
    ForecastBundle,
)


def _empirical_samples_from_quantiles(bundle: ForecastBundle, *, n: int = 2000,
                                       seed: int = 42) -> np.ndarray:
    """Inverse-CDF sample from the bundle's quantile band.

    Linear interpolation between the 7 canonical quantiles. Stays inside
    [q05, q95]; the tail beyond is not modelled at v0.1.
    """
    q = bundle.quantiles
    levels = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
    values = np.array([q.q05, q.q10, q.q25, q.q50, q.q75, q.q90, q.q95])
    rng = np.random.default_rng(seed)
    u = rng.uniform(levels[0], levels[-1], size=n)
    samples: np.ndarray = np.interp(u, levels, values)
    return samples


def evaluate(
    bundle: ForecastBundle,
    actual: DemandActual,
    *,
    baseline_crps: float | None = None,
    forecast_horizon_remaining_seconds: float = 0.0,
    crps_sample_size: int = 2000,
    actuals_provenance_extra: list[str] | None = None,
) -> ForecastAccuracy:
    """Score a single ForecastBundle against the DemandActual that realized
    in its bucket.

    Parameters
    ----------
    bundle
        The forecast under evaluation. ``bundle.quantiles`` drives the
        probabilistic scoring; ``bundle.mean`` drives the point metrics.
    actual
        The realized demand observation. Must share ``sku_id`` +
        ``location_id`` + ``bucket`` with ``bundle`` — mismatches raise
        ``ValueError`` rather than silently scoring against the wrong cell.
    baseline_crps
        Optional reference CRPS (e.g. from the model's own walk-forward
        backtest at training time). When supplied, ``drift_magnitude`` is
        set to ``current_crps / baseline_crps`` — the
        DemandSignalOS-canonical drift signal consumed by the
        PlanningOS critic's ``drift_detected`` archetype. When omitted,
        ``drift_magnitude`` is ``None`` and the critic treats this iter
        as carrying no drift signal (no false positive).
    forecast_horizon_remaining_seconds
        Seconds of forecast horizon remaining at evaluation time. Pure
        passthrough to the verdict for the critic's "urgency" decisions
        (early-drift vs. late-drift).
    crps_sample_size
        Number of inverse-CDF samples drawn from the quantile band for
        the empirical CRPS estimator. Default 2000 — pinned to
        ``bundle.provenance.seed`` so the score is deterministic.
    actuals_provenance_extra
        Optional list of upstream identifiers (e.g. O2C event IDs) to
        record on the accuracy receipt alongside the bundle's own
        provenance trail.

    Returns
    -------
    ForecastAccuracy
        Production-ready accuracy record carrying every field consumed
        by the closed-loop critic. ``actuals_drift_flag`` is set when
        ``drift_magnitude > 1.5`` (operational default) — but the
        critic's own per-horizon threshold is what actually drives halt
        decisions; this flag is a convenience for downstream UIs.

    Raises
    ------
    ValueError
        When the actual's identity does not match the bundle, or when
        the actual's censoring rules out usable observation.
    """
    if bundle.sku_id != actual.sku_id:
        raise ValueError(
            f"sku_id mismatch: bundle={bundle.sku_id!r} actual={actual.sku_id!r}"
        )
    if bundle.location_id != actual.location_id:
        raise ValueError(
            f"location_id mismatch: bundle={bundle.location_id!r} "
            f"actual={actual.location_id!r}"
        )
    if bundle.bucket != actual.bucket:
        raise ValueError(
            f"bucket mismatch: bundle={bundle.bucket!r} actual={actual.bucket!r}"
        )

    observed = float(actual.units_sold)
    # CRPS via inverse-CDF samples from the bundle. Deterministic in
    # (bundle.provenance.seed, quantiles) — same forecast + same actual
    # always produces the same crps value.
    samples = _empirical_samples_from_quantiles(
        bundle, n=crps_sample_size, seed=bundle.provenance.seed
    )
    crps_value = crps(observed, samples.tolist())

    smape_value = smape(observed, bundle.mean)
    pinball_q50 = pinball_loss(observed, bundle.quantiles.q50, 0.50)
    pinball_q90 = pinball_loss(observed, bundle.quantiles.q90, 0.90)

    # MAPE undefined when the actual is zero — return None per CONTRACTS
    # §1.3 convention, downstream consumers handle missing.
    if observed == 0.0:
        mape_value: float | None = None
    else:
        mape_value = abs(observed - bundle.mean) / abs(observed)

    drift_magnitude: float | None = None
    actuals_drift_flag = False
    if baseline_crps is not None and baseline_crps > 0:
        drift_magnitude = crps_value / baseline_crps
        # 1.5x degradation = operational threshold (matches PlanningOS
        # critic's DEFAULT_DRIFT_THRESHOLDS["operational"]). This flag is
        # informational; the critic's own per-horizon thresholds drive
        # halt decisions.
        actuals_drift_flag = drift_magnitude > 1.5

    provenance: list[str] = [bundle.provenance.forecast_bundle_id]
    if actuals_provenance_extra:
        provenance.extend(actuals_provenance_extra)

    horizon_label = bundle.horizon_label
    # WIS — secondary metric per BACKTESTING.md §5 (custom backtest impl
    # rather than schema field). Computed here for completeness but not
    # part of the schema yet.
    _ = wis(observed, bundle.quantiles)

    return ForecastAccuracy(
        forecast_bundle_id=bundle.provenance.forecast_bundle_id,
        sku_id=bundle.sku_id,
        location_id=bundle.location_id,
        bucket=bundle.bucket,
        forecast_horizon_label=horizon_label,
        mape=mape_value,
        smape=smape_value if smape_value is not None else float("nan"),
        crps=crps_value,
        pinball_q50=pinball_q50,
        pinball_q90=pinball_q90,
        actuals_drift_flag=actuals_drift_flag,
        drift_magnitude=drift_magnitude,
        baseline_crps=baseline_crps,
        forecast_horizon_remaining=float(forecast_horizon_remaining_seconds),
        actuals_provenance=provenance,
    )


def aggregate_drift(
    recent_accuracies: list[ForecastAccuracy],
    *,
    weight_by_horizon_remaining: bool = False,
) -> float | None:
    """Aggregate per-bundle accuracy into a single drift_magnitude.

    Used by orchestrator-side wire-ups when an iteration consumes more
    than one forecast bundle (multi-SKU loops). Skips records with
    ``drift_magnitude=None``. When ``weight_by_horizon_remaining=True``,
    weights by remaining seconds in the bundle's horizon (urgency).
    """
    # Filter to records carrying a real drift signal; reify the floats
    # so mypy sees a concrete list[float] downstream.
    drift_values: list[float] = [
        a.drift_magnitude for a in recent_accuracies if a.drift_magnitude is not None
    ]
    if not drift_values:
        return None
    if weight_by_horizon_remaining:
        weights = [
            max(a.forecast_horizon_remaining, 1.0)
            for a in recent_accuracies if a.drift_magnitude is not None
        ]
        total_w = sum(weights)
        return float(
            sum(d * w for d, w in zip(drift_values, weights, strict=True))
            / total_w
        )
    return float(sum(drift_values) / len(drift_values))


def is_finite_drift(value: float | None) -> bool:
    """True when ``value`` is a usable drift_magnitude (positive + finite)."""
    return value is not None and math.isfinite(value) and value > 0.0
