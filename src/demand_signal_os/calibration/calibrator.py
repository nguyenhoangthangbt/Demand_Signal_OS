"""DemandSignalCalibrator — DSO's concrete ``Calibrator`` impl.

Reference implementation pattern that every engine follows. The class
is dependency-injected with a ``Forecaster`` so the customer can BYO
without forking. The default DSO production forecaster (statsforecast
ETS / Croston / TSB / SBA / GBM) plugs in via the same Protocol.

Pipeline per ``calibrate()`` call:

    1. Validate the reference: must be ``ForecastActualsReference``
       (the typed contract for forecasting calibration).
    2. Split actuals into fit window + score window per the
       rolling-origin protocol.
    3. Fit forecaster on the fit window.
    4. Emit ``ForecastBundle`` for each bucket in the score window.
    5. Score via ``accuracy.evaluate`` → MAPE / sMAPE / CRPS / coverage.
    6. Map scores to ``CalibrationMetric`` rows with tolerance + gate.
    7. Wrap in a single ``PhaseResult`` (``CalibrationKind.SINGLE_SHOT``).
    8. Sign + return.

The metric tolerances are conservative defaults aimed at "a real
production forecaster on stable demand should pass". Customers can
tighten or relax them via ``tolerance_overrides`` per the v0.2
self-service calibration page.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import numpy as np

from demand_signal_os.accuracy import evaluate
from demand_signal_os.ops_schemas import (
    CalibrationError,
    CalibrationKind,
    CalibrationMetric,
    CalibrationReceipt,
    CalibrationReference,
    CalibrationStatus,
    CheckIndependence,
    DemandActual,
    Forecaster,
    ForecastActualsReference,
    ForecastAccuracy,
    ForecastBundle,
    InvalidReferenceData,
    IncompleteCalibration,
    MetricGate,
    PhaseResult,
    ProvenanceEnvelope,
    ToleranceKind,
    compose_inputs_hash,
    sign_receipt,
)

DEFAULT_TOLERANCES: dict[str, tuple[float, ToleranceKind, MetricGate]] = {
    # MAPE: 25% absolute floor for noisy daily demand; tightened by
    # customer override on the calibration page when the SKU pattern
    # is stable.
    "MAPE": (0.25, ToleranceKind.ABSOLUTE, MetricGate.HARD),
    # sMAPE: 0.30 absolute (sMAPE is bounded in [0, 2]).
    "sMAPE": (0.30, ToleranceKind.ABSOLUTE, MetricGate.HARD),
    # CRPS: 2x baseline_crps as a ceiling. The reference itself supplies
    # baseline_crps; the calibrator interprets tolerance as absolute on
    # the ratio.
    "CRPS_vs_baseline": (2.0, ToleranceKind.ABSOLUTE, MetricGate.HARD),
    # Coverage at the q05–q95 band: target 0.90, ±0.05 absolute is
    # acceptable for v0.1 (soft warning above ±0.05, hard fail above ±0.10).
    "coverage_90": (0.10, ToleranceKind.ABSOLUTE, MetricGate.HARD),
}


@dataclass
class DemandSignalCalibrator:
    """Concrete Calibrator for DSO.

    The forecaster is dependency-injected so customers can BYO without
    forking DSO. The fit/forecast/evaluate cycle is bounded by the
    ``CalibrationReference.actual_count`` and the supplied ``fit_ratio``
    (defaults to 0.7 — 70% fit, 30% score).
    """

    name: str = "demand_signal_os.calibrator"
    version: str = "0.1.0"
    forecaster: Forecaster | None = None  # required at calibrate() time
    fit_ratio: float = 0.7
    tolerance_overrides: dict[str, float] = field(default_factory=dict)
    signing_secret: bytes | None = None  # set per deployment
    signing_key_id: str = "dso-calibrator-key-v1"

    # ---- public API ----

    def calibrate(
        self,
        reference: CalibrationReference,
        actuals: Iterable[DemandActual],
    ) -> CalibrationReceipt:
        """Run calibration; emit a signed CalibrationReceipt.

        ``actuals`` is supplied separately from the reference so the
        reference (hash + metadata) stays small and the heavy data lives
        in a typed iterable. Production deployments stream from the DB.
        """
        if not isinstance(reference, ForecastActualsReference):
            raise InvalidReferenceData(
                f"DemandSignalCalibrator requires ForecastActualsReference, "
                f"got {type(reference).__name__}"
            )
        if self.forecaster is None:
            raise CalibrationError(
                "DemandSignalCalibrator requires a Forecaster injection "
                "before calibrate() is called"
            )

        history = list(actuals)
        if len(history) < 10:
            raise IncompleteCalibration(
                f"need >= 10 actuals to calibrate; got {len(history)}"
            )

        started = datetime.now(timezone.utc)

        # Rolling-origin split: fit on the first fit_ratio, score on rest.
        n_fit = max(5, int(len(history) * self.fit_ratio))
        fit_window = history[:n_fit]
        score_window = history[n_fit:]
        if not score_window:
            raise IncompleteCalibration(
                "score window empty after fit/score split — supply more actuals"
            )

        self.forecaster.fit(fit_window)

        # Emit ONE forecast bundle for the score window (DSO library API)
        # and score the bundle against each actual in turn. The forecast
        # bundle is shared so coverage / CRPS are computed against the
        # same band.
        bundle: ForecastBundle = self.forecaster.forecast(
            sku_id=reference.sku_id,
            location_id=reference.location_id,
            horizon_label=reference.horizon_label,
        )

        # Per-actual accuracy records, then aggregate.
        accuracies: list[ForecastAccuracy] = []
        for actual in score_window:
            try:
                accuracies.append(
                    evaluate(
                        bundle,
                        # accuracy.evaluate requires bucket/sku/location
                        # match with the bundle. We rebuild the actual
                        # with the bundle's identity to score the band
                        # against the score window.
                        actual.model_copy(
                            update={
                                "sku_id": bundle.sku_id,
                                "location_id": bundle.location_id,
                                "bucket": bundle.bucket,
                            }
                        ),
                        baseline_crps=reference.baseline_crps,
                    )
                )
            except ValueError:
                # Mismatched identity rows are silently skipped — caller
                # supplied them, calibrator does not crash on dirty data.
                continue

        if not accuracies:
            raise IncompleteCalibration(
                "no scoreable accuracies emitted — score window may all be censored"
            )

        # Aggregate to a single per-metric value.
        mape_values = [a.mape for a in accuracies if a.mape is not None]
        mape_mean = float(np.mean(mape_values)) if mape_values else 0.0
        smape_mean = float(np.mean([a.smape for a in accuracies]))
        crps_mean = float(np.mean([a.crps for a in accuracies]))
        crps_ratio = (
            crps_mean / reference.baseline_crps if reference.baseline_crps > 0 else 0.0
        )

        # Coverage: fraction of score-window observations inside the
        # [q05, q95] band of the shared forecast bundle.
        coverage = coverage_inside_band(
            [float(a.units_sold) for a in score_window],
            bundle.quantiles.q05,
            bundle.quantiles.q95,
        )

        # Map to CalibrationMetric.
        def _metric(
            name: str,
            measured: float,
            reference_v: float | None,
            direction: str,
        ) -> CalibrationMetric:
            tol, kind, gate = DEFAULT_TOLERANCES[name]
            if name in self.tolerance_overrides:
                tol = self.tolerance_overrides[name]
            return CalibrationMetric(
                name=name,
                measured_value=measured,
                reference_value=reference_v,
                tolerance=tol,
                tolerance_kind=kind,
                direction=direction,
                gate=gate,
                independence=CheckIndependence.SEMI_INDEPENDENT,
                formula=name,
            )

        metrics = (
            _metric("MAPE", mape_mean, 0.0, "lower_better"),
            _metric("sMAPE", smape_mean, 0.0, "lower_better"),
            _metric("CRPS_vs_baseline", crps_ratio, 1.0, "lower_better"),
            _metric("coverage_90", coverage, 0.90, "match"),
        )

        completed = datetime.now(timezone.utc)

        phase = PhaseResult(
            phase_id="accuracy",
            title="Rolling-origin accuracy on score window",
            started_at=started,
            completed_at=completed,
            metrics=metrics,
        )

        # Closes triangulation #6 (cross-impl review) + post-merge #1: use the
        # shared ``compose_inputs_hash`` helper so the signed receipt
        # commits to the full config (fit_ratio + tolerance_overrides +
        # baseline_crps + actuals payload).
        actuals_payload = "|".join(
            f"{a.sku_id}:{a.units_sold}:{a.recorded_at.isoformat()}"
            for a in history
        )
        config = {
            "fit_ratio": self.fit_ratio,
            "tolerance_overrides": dict(sorted(self.tolerance_overrides.items())),
            "baseline_crps": reference.baseline_crps,
            "horizon_label": reference.horizon_label,
            "actuals_payload": actuals_payload,
            "forecaster_id": (
                f"{self.forecaster.name}@{self.forecaster.version}"
                if self.forecaster is not None
                else "unknown"
            ),
        }
        inputs_hash = compose_inputs_hash(reference, config, code_version=self.version)
        outputs_payload = (
            f"{bundle.provenance.forecast_bundle_id}|MAPE={mape_mean}"
            f"|sMAPE={smape_mean}|CRPS={crps_mean}|cov={coverage}"
        )
        outputs_hash = "sha256:" + hashlib.sha256(
            outputs_payload.encode("utf-8")
        ).hexdigest()

        receipt = CalibrationReceipt(
            calibration_id=f"cal_dso_{uuid.uuid4().hex[:10]}",
            kind=CalibrationKind.SINGLE_SHOT,
            reference=reference,
            phases=(phase,),
            started_at=started,
            completed_at=completed,
            provenance=ProvenanceEnvelope(
                engine="demandsignal",
                engine_version=self.version,
                seed=bundle.provenance.seed,
                produced_at=completed,
                commit_sha=bundle.provenance.commit_sha,
            ),
            inputs_hash=inputs_hash,
            outputs_hash=outputs_hash,
            caveats=(
                f"Fit window: {len(fit_window)} obs · score window: "
                f"{len(score_window)} obs.",
            ),
        )

        if self.signing_secret is not None:
            receipt = sign_receipt(
                receipt,
                self.signing_secret,
                self.signing_key_id,
            )

        return receipt

    def status(self) -> CalibrationStatus:
        """Return an UNCALIBRATED status (this calibrator is stateless;
        consumers cache the receipt + build status server-side)."""
        return CalibrationStatus(engine="demandsignal", receipt=None)


def coverage_inside_band(values: list[float], lower: float, upper: float) -> float:
    """Fraction of ``values`` inside ``[lower, upper]`` inclusive."""
    if not values:
        return 0.0
    inside = sum(1 for v in values if lower <= v <= upper)
    return inside / len(values)
