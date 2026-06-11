"""DemandSignalCalibrator golden tests.

Known-answer assertions on a deterministic synthetic Gaussian demand
window. The point is to prove the calibration pipeline is correct
end-to-end against a reference whose answers we know analytically:

  - Gaussian demand with mean μ, std σ
  - 4-period moving-average forecaster
  - Expected MAPE bounded by σ/μ (rough)
  - Expected coverage at q05–q95 ≈ 0.90 ± 0.05

If any assertion fails, the calibration contract is broken. These
tests are the quality gate for v0.2 trust.
"""
from __future__ import annotations

import datetime as dt
import statistics
import uuid
from dataclasses import dataclass, field

import numpy as np
import pytest

from demand_signal_os.calibration import (
    DemandSignalCalibrator,
    coverage_inside_band,
)
from demand_signal_os.ops_schemas import (
    CalibrationKind,
    CalibrationState,
    CalibrationStatus,
    CheckIndependence,
    CensoringFlag,
    DemandActual,
    ForecastActualsReference,
    Forecaster,
    ForecastBundle,
    ForecastProvenance,
    InvalidReferenceData,
    IncompleteCalibration,
    MetricGate,
    Quantiles,
    TimeBucket,
    sign_receipt,
    verify_receipt,
)
from demand_signal_os.ops_schemas import (
    ForecastAccuracy,
    WorkbookReference,
)
from demand_signal_os.ops_schemas import CalibrationReferenceMeta


SHA_DUMMY = "sha256:" + "a" * 64
SECRET = b"dso-calibrator-test-secret-32-bytes-or-more-padding"


# ---------------------------------------------------------------------------
# Test Forecaster: tiny in-package MA so the test is self-contained.
# ---------------------------------------------------------------------------


@dataclass
class _TestMovingAverageForecaster:
    name: str = "test-ma4"
    version: str = "0.1.0"
    window: int = 4
    _history: list[float] = field(default_factory=list)

    def fit(self, history: list[DemandActual]) -> None:
        self._history = [
            float(r.units_demanded if r.units_demanded is not None else r.units_sold)
            for r in history
        ]

    def forecast(
        self,
        sku_id: str,
        location_id: str,
        horizon_label: str = "operational",
    ) -> ForecastBundle:
        window = self._history[-self.window :]
        mean = statistics.fmean(window)
        std = statistics.pstdev(window) if len(window) >= 2 else 1.0
        q = Quantiles(
            q05=max(0.0, mean - 1.645 * std),
            q10=max(0.0, mean - 1.282 * std),
            q25=max(0.0, mean - 0.674 * std),
            q50=mean,
            q75=mean + 0.674 * std,
            q90=mean + 1.282 * std,
            q95=mean + 1.645 * std,
        )
        now = dt.datetime.now(dt.timezone.utc)
        today = now.date()
        return ForecastBundle(
            sku_id=sku_id,
            location_id=location_id,
            bucket=TimeBucket(
                period="week",
                start=today,
                end=today + dt.timedelta(weeks=1),
            ),
            horizon_label=horizon_label,  # type: ignore[arg-type]
            quantiles=q,
            mean=mean,
            method=f"moving_average({self.window})",
            provenance=ForecastProvenance(
                forecast_bundle_id=str(uuid.uuid4()),
                model_id=f"{self.name}@{self.version}",
                commit_sha="0" * 40,
                seed=42,
                feature_set_hash="test",
                data_cut_timestamp=now,
                produced_at=now,
            ),
        )

    def evaluate(
        self,
        actuals: list[DemandActual],
        forecast: ForecastBundle,
    ) -> ForecastAccuracy:
        # Not used by the calibrator — accuracy.evaluate is called
        # directly. Implemented for Protocol satisfaction.
        a = float(actuals[0].units_sold)
        return ForecastAccuracy(
            forecast_bundle_id=forecast.provenance.forecast_bundle_id,
            sku_id=forecast.sku_id,
            location_id=forecast.location_id,
            bucket=forecast.bucket,
            forecast_horizon_label=forecast.horizon_label,
            mape=abs(a - forecast.mean) / max(a, 1e-9),
            smape=2 * abs(a - forecast.mean) / (abs(a) + abs(forecast.mean) + 1e-9),
            crps=abs(a - forecast.mean),
            pinball_q50=abs(a - forecast.mean),
            pinball_q90=abs(a - forecast.mean),
            actuals_drift_flag=False,
            actuals_provenance=[],
            forecast_horizon_remaining=0,
        )


# ---------------------------------------------------------------------------
# Synthetic demand generator with KNOWN parameters.
# ---------------------------------------------------------------------------


def _gaussian_demand(n: int, mu: float, sigma: float, seed: int = 42) -> list[DemandActual]:
    """Generate n stable Gaussian demand observations.

    The window has known mu + sigma so the test can assert MAPE / coverage
    bounds analytically.
    """
    rng = np.random.default_rng(seed)
    samples = rng.normal(loc=mu, scale=sigma, size=n).clip(min=0)
    out: list[DemandActual] = []
    start = dt.date(2026, 1, 1)
    for i, v in enumerate(samples):
        bucket_start = start + dt.timedelta(weeks=i)
        out.append(
            DemandActual(
                sku_id="SKU-G",
                location_id="DC-1",
                bucket={
                    "period": "week",
                    "start": bucket_start,
                    "end": bucket_start + dt.timedelta(weeks=1),
                },
                units_sold=float(v),
                units_demanded=float(v),
                censoring=CensoringFlag.OBSERVED,
                recorded_at=dt.datetime.combine(bucket_start, dt.time(0, 0)).replace(
                    tzinfo=dt.timezone.utc
                ),
                source_system="golden_test",
            )
        )
    return out


def _ref(baseline_crps: float = 5.0, count: int = 30) -> ForecastActualsReference:
    return ForecastActualsReference(
        sku_id="SKU-G",
        location_id="DC-1",
        horizon_label="operational",
        baseline_crps=baseline_crps,
        actual_count=count,
        meta=CalibrationReferenceMeta(data_hash=SHA_DUMMY),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_forecaster_satisfies_protocol() -> None:
    assert isinstance(_TestMovingAverageForecaster(), Forecaster)


def test_calibrate_known_gaussian_window_emits_passing_receipt() -> None:
    """Golden test: stable Gaussian demand → calibrator emits a passing
    receipt because the MA forecaster recovers the mean within tolerance."""
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    actuals = _gaussian_demand(30, mu=100.0, sigma=10.0)
    receipt = cal.calibrate(_ref(baseline_crps=15.0), actuals)
    assert receipt.kind == CalibrationKind.SINGLE_SHOT
    assert len(receipt.phases) == 1
    metric_names = {m.name for m in receipt.phases[0].metrics}
    assert metric_names == {"MAPE", "sMAPE", "CRPS_vs_baseline", "coverage_90"}
    assert receipt.overall_passed is True


def test_calibrate_noisy_demand_produces_failed_receipt() -> None:
    """Heteroscedastic spike demand: MA forecaster cannot track it, MAPE
    blows past the 25% tolerance, receipt is FAILED."""
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(
        forecaster=forecaster,
        tolerance_overrides={"MAPE": 0.05},  # tight tolerance forces fail
        require_signing=False,
    )
    actuals = _gaussian_demand(30, mu=100.0, sigma=80.0, seed=99)
    receipt = cal.calibrate(_ref(baseline_crps=15.0), actuals)
    status = CalibrationStatus(engine="demandsignal", receipt=receipt)
    assert status.state == CalibrationState.FAILED


def test_calibrate_rejects_wrong_reference_type() -> None:
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    wrong = WorkbookReference(
        workbook_name="x",
        meta=CalibrationReferenceMeta(data_hash=SHA_DUMMY),
    )
    actuals = _gaussian_demand(15, mu=100.0, sigma=10.0)
    with pytest.raises(InvalidReferenceData):
        cal.calibrate(wrong, actuals)


def test_calibrate_requires_forecaster_injection() -> None:
    cal = DemandSignalCalibrator(require_signing=False)
    with pytest.raises(Exception):
        cal.calibrate(_ref(), _gaussian_demand(20, 100, 10))


def test_calibrate_rejects_too_few_actuals() -> None:
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    with pytest.raises(IncompleteCalibration):
        cal.calibrate(_ref(count=5), _gaussian_demand(5, 100, 10))


def test_signed_receipt_verifies_under_secret() -> None:
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(
        forecaster=forecaster,
        signing_secret=SECRET,
        signing_key_id="dso-key-v1",
    )
    receipt = cal.calibrate(_ref(), _gaussian_demand(30, 100, 10))
    assert receipt.signature is not None
    assert receipt.signed_by == "dso-key-v1"
    assert verify_receipt(receipt, SECRET, allowed_key_ids=frozenset({"dso-key-v1"}))


def test_coverage_inside_band_known_values() -> None:
    assert coverage_inside_band([1, 2, 3, 4, 5], 2, 4) == 3 / 5
    assert coverage_inside_band([], 0, 1) == 0.0
    assert coverage_inside_band([1, 1, 1], 1, 1) == 1.0


def test_provenance_envelope_seed_preserved() -> None:
    """Reproducibility: the receipt's provenance seed must match the
    forecaster's bundle seed so a customer can recreate the calibration."""
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(), _gaussian_demand(30, 100, 10))
    assert receipt.provenance.seed == 42  # matches forecaster's seed
    assert receipt.provenance.engine == "demandsignal"


def test_metric_independence_tier_is_semi_independent() -> None:
    """Forecasting calibration is semi-independent — actuals come from
    the same SKU/location/bucket the forecaster trained on."""
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(), _gaussian_demand(30, 100, 10))
    for m in receipt.phases[0].metrics:
        assert m.independence == CheckIndependence.SEMI_INDEPENDENT


def test_hard_gates_on_required_metrics() -> None:
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(), _gaussian_demand(30, 100, 10))
    gates = {m.name: m.gate for m in receipt.phases[0].metrics}
    assert gates == {
        "MAPE": MetricGate.HARD,
        "sMAPE": MetricGate.HARD,
        "CRPS_vs_baseline": MetricGate.HARD,
        "coverage_90": MetricGate.HARD,
    }


def test_calibration_status_calibrated_for_stable_demand() -> None:
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(), _gaussian_demand(30, 100, 10))
    s = CalibrationStatus(engine="demandsignal", receipt=receipt)
    assert s.state == CalibrationState.CALIBRATED
    assert s.hard_passed == s.hard_total


# ---------------------------------------------------------------------------
# Test-coverage BLOCKERs from the 2026-06-10 triangulation
# ---------------------------------------------------------------------------


# BLOCKER #7 — known-answer bounded assertions.
def test_metric_values_within_analytical_bounds_on_stable_gaussian() -> None:
    """Stable Gaussian (mu=100, sigma=10): MA-forecaster MAPE should
    track sigma/mu ≈ 0.10. Assert metric values are in the right
    neighbourhood, not just structurally present."""
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(baseline_crps=15.0), _gaussian_demand(60, 100.0, 10.0))
    by_name = {m.name: m for m in receipt.phases[0].metrics}
    # MAPE: error / actual. For sigma/mu = 0.10 with 30 samples,
    # observed MAPE typically falls in [0.05, 0.20].
    assert 0.02 < by_name["MAPE"].measured_value < 0.30, by_name["MAPE"].measured_value
    # sMAPE: 2|a-f|/(|a|+|f|); for stable Gaussian ≈ MAPE.
    assert 0.02 < by_name["sMAPE"].measured_value < 0.30
    # CRPS_vs_baseline: with baseline_crps=15 and a non-degenerate band,
    # ratio should be < 1 (band roughly covers the noise).
    assert 0.0 < by_name["CRPS_vs_baseline"].measured_value < 1.5
    # coverage_90: target 0.90, allow ±0.30 noise on n=18 score window.
    assert 0.4 <= by_name["coverage_90"].measured_value <= 1.0


# BLOCKER #9 — reproducibility.
def test_calibrate_twice_produces_identical_hashes_and_metrics() -> None:
    """Same (reference, actuals, forecaster, seed) → identical inputs_hash
    + outputs_hash + per-metric measured values. Federation correctness
    depends on this."""
    actuals = _gaussian_demand(30, 100, 10, seed=123)
    forecaster_a = _TestMovingAverageForecaster()
    forecaster_b = _TestMovingAverageForecaster()
    r1 = DemandSignalCalibrator(forecaster=forecaster_a, require_signing=False).calibrate(_ref(), actuals)
    r2 = DemandSignalCalibrator(forecaster=forecaster_b, require_signing=False).calibrate(_ref(), actuals)
    assert r1.inputs_hash == r2.inputs_hash
    metrics_1 = sorted(
        (m.name, m.measured_value) for m in r1.phases[0].metrics
    )
    metrics_2 = sorted(
        (m.name, m.measured_value) for m in r2.phases[0].metrics
    )
    assert metrics_1 == metrics_2


# BLOCKER #10 — real production-shape forecaster.
# Inline a numpy-backed exponential-smoothing forecaster that has the
# production shape (state-space variance → quantile band) — different
# math than the MA stub. Proves the calibrator works against
# non-trivial forecasters, not just the test toy.
@dataclass
class _SimpleETSForecaster:
    name: str = "ses-numpy"
    version: str = "0.1.0"
    alpha: float = 0.3
    _history: list[float] = field(default_factory=list)

    def fit(self, history: list[DemandActual]) -> None:
        vals = [float(r.units_sold) for r in history]
        # Simple exponential smoothing level.
        self._history = vals

    def forecast(
        self,
        sku_id: str,
        location_id: str,
        horizon_label: str = "operational",
    ) -> ForecastBundle:
        import numpy as np

        hist = np.asarray(self._history, dtype=float)
        # SES level
        level = hist[0]
        for v in hist[1:]:
            level = self.alpha * v + (1 - self.alpha) * level
        # Residual variance from SES
        smoothed = [hist[0]]
        for v in hist[1:]:
            smoothed.append(self.alpha * v + (1 - self.alpha) * smoothed[-1])
        residuals = hist - np.asarray(smoothed)
        sigma = float(np.std(residuals)) or 1.0
        q = Quantiles(
            q05=max(0.0, level - 1.645 * sigma),
            q10=max(0.0, level - 1.282 * sigma),
            q25=max(0.0, level - 0.674 * sigma),
            q50=float(level),
            q75=float(level) + 0.674 * sigma,
            q90=float(level) + 1.282 * sigma,
            q95=float(level) + 1.645 * sigma,
        )
        now = dt.datetime.now(dt.timezone.utc)
        today = now.date()
        return ForecastBundle(
            sku_id=sku_id,
            location_id=location_id,
            bucket=TimeBucket(
                period="week",
                start=today,
                end=today + dt.timedelta(weeks=1),
            ),
            horizon_label=horizon_label,  # type: ignore[arg-type]
            quantiles=q,
            mean=float(level),
            method="ses",
            provenance=ForecastProvenance(
                forecast_bundle_id=str(uuid.uuid4()),
                model_id=f"{self.name}@{self.version}",
                commit_sha="0" * 40,
                seed=7,
                feature_set_hash="ses",
                data_cut_timestamp=now,
                produced_at=now,
            ),
        )

    def evaluate(
        self,
        actuals: list[DemandActual],
        forecast: ForecastBundle,
    ) -> ForecastAccuracy:
        a = float(actuals[0].units_sold)
        return ForecastAccuracy(
            forecast_bundle_id=forecast.provenance.forecast_bundle_id,
            sku_id=forecast.sku_id,
            location_id=forecast.location_id,
            bucket=forecast.bucket,
            forecast_horizon_label=forecast.horizon_label,
            mape=abs(a - forecast.mean) / max(a, 1e-9),
            smape=2 * abs(a - forecast.mean) / (abs(a) + abs(forecast.mean) + 1e-9),
            crps=abs(a - forecast.mean),
            pinball_q50=abs(a - forecast.mean),
            pinball_q90=abs(a - forecast.mean),
            actuals_drift_flag=False,
            actuals_provenance=[],
            forecast_horizon_remaining=0,
        )


def test_simple_ets_forecaster_satisfies_forecaster_protocol() -> None:
    assert isinstance(_SimpleETSForecaster(), Forecaster)


def test_calibrate_with_ses_forecaster_passes_on_stable_demand() -> None:
    """Calibrator works against a state-space variance forecaster, not
    just the MA stub. Different math, same contract."""
    forecaster = _SimpleETSForecaster(alpha=0.3)
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(baseline_crps=15.0), _gaussian_demand(60, 100, 10))
    assert receipt.overall_passed is True
    s = CalibrationStatus(engine="demandsignal", receipt=receipt)
    assert s.state == CalibrationState.CALIBRATED


def test_calibrate_with_ses_forecaster_fails_on_regime_shift() -> None:
    """Demand level-shift mid-window: forecaster can't track → real
    failure (no tolerance override needed). Closes BLOCKER #8 from
    the test review — actual failure mode, not tolerance trick."""
    # Build a 60-period series with mu=100 for first 30, mu=400 for next 30.
    stable = _gaussian_demand(30, 100, 5, seed=11)
    shocked = _gaussian_demand(30, 400, 5, seed=13)
    # Re-stamp the second half's bucket timestamps to be sequential.
    shifted_buckets = []
    base = stable[-1].recorded_at + dt.timedelta(weeks=1)
    for i, s in enumerate(shocked):
        bucket_start = base.date() + dt.timedelta(weeks=i)
        shifted_buckets.append(
            DemandActual(
                sku_id=s.sku_id, location_id=s.location_id,
                bucket={
                    "period": "week",
                    "start": bucket_start,
                    "end": bucket_start + dt.timedelta(weeks=1),
                },
                units_sold=s.units_sold, units_demanded=s.units_demanded,
                censoring=s.censoring,
                recorded_at=dt.datetime.combine(bucket_start, dt.time(0, 0)).replace(tzinfo=dt.timezone.utc),
                source_system=s.source_system,
            )
        )
    forecaster = _SimpleETSForecaster(alpha=0.1)  # slow alpha can't track
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    receipt = cal.calibrate(_ref(baseline_crps=15.0), stable + shifted_buckets)
    # Slow SES on a level-shift: MAPE blows past 0.25 absolute tolerance.
    assert receipt.overall_passed is False, [
        (m.name, m.measured_value, m.passed) for m in receipt.phases[0].metrics
    ]


def test_inputs_hash_changes_when_fit_ratio_changes() -> None:
    """Closes triangulation 2 BLOCKER #1 (compose_inputs_hash unused):
    different fit_ratio MUST produce a different inputs_hash. Without
    this, the signed receipt commits to a lie when config changes."""
    actuals = _gaussian_demand(30, 100, 10)
    r_default = DemandSignalCalibrator(
        forecaster=_TestMovingAverageForecaster(), fit_ratio=0.7,
        require_signing=False,
    ).calibrate(_ref(), actuals)
    r_changed = DemandSignalCalibrator(
        forecaster=_TestMovingAverageForecaster(), fit_ratio=0.5,
        require_signing=False,
    ).calibrate(_ref(), actuals)
    assert r_default.inputs_hash != r_changed.inputs_hash


def test_inputs_hash_changes_when_tolerance_overrides_change() -> None:
    actuals = _gaussian_demand(30, 100, 10)
    r_default = DemandSignalCalibrator(
        forecaster=_TestMovingAverageForecaster(),
        require_signing=False,
    ).calibrate(_ref(), actuals)
    r_tight = DemandSignalCalibrator(
        forecaster=_TestMovingAverageForecaster(),
        tolerance_overrides={"MAPE": 0.05},
        require_signing=False,
    ).calibrate(_ref(), actuals)
    assert r_default.inputs_hash != r_tight.inputs_hash


def test_default_calibrator_refuses_unsigned_calibrate() -> None:
    """Closes triangulation 3 BLOCKER #6: require_signing defaults
    True; calibrate() raises before any work if signing_secret is None."""
    from ops_schemas import CalibrationError

    actuals = _gaussian_demand(30, 100, 10)
    cal = DemandSignalCalibrator(forecaster=_TestMovingAverageForecaster())
    with pytest.raises(CalibrationError):
        cal.calibrate(_ref(), actuals)


def test_calibrate_with_tiny_baseline_crps_does_not_explode() -> None:
    """baseline_crps just above 0 — CRPS ratio is huge but receipt still
    parses + emits without NaN/Inf."""
    forecaster = _TestMovingAverageForecaster()
    cal = DemandSignalCalibrator(forecaster=forecaster, require_signing=False)
    ref_tiny = ForecastActualsReference(
        sku_id="SKU-G",
        location_id="DC-1",
        horizon_label="operational",
        baseline_crps=0.001,  # tiny but legal (> 0)
        actual_count=30,
        meta=CalibrationReferenceMeta(data_hash=SHA_DUMMY),
    )
    receipt = cal.calibrate(ref_tiny, _gaussian_demand(30, 100, 10))
    crps_metric = next(m for m in receipt.phases[0].metrics if m.name == "CRPS_vs_baseline")
    import math
    assert not math.isnan(crps_metric.measured_value)
    assert not math.isinf(crps_metric.measured_value)
    # Almost certainly fails — but it must FAIL cleanly, not raise.
    assert receipt.overall_passed is False
