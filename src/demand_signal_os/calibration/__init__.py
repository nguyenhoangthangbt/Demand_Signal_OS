"""Calibration surface for DemandSignalOS.

Per the v0.2 calibration plan (2026-06-09): DSO implements the
``Calibrator`` Protocol from ``ops_schemas.protocols`` so Plan2Cash
can federate trust state per engine.

This package provides the concrete ``DemandSignalCalibrator`` that:
  - reads a ``ForecastActualsReference`` (typed contract; no bytes),
  - runs the injected ``Forecaster`` against the reference window,
  - scores via ``demand_signal_os.accuracy.evaluate``,
  - emits a signed, tamper-evident ``CalibrationReceipt`` with
    MAPE / sMAPE / CRPS / coverage_90 metrics.

The golden test in ``tests/test_calibrator.py`` exercises the
end-to-end pipeline against a known-answer synthetic Gaussian demand
window so the contract is verified before any real engine wires it.
"""
from __future__ import annotations

from demand_signal_os.calibration.calibrator import (
    DemandSignalCalibrator,
    coverage_inside_band,
)

__all__ = [
    "DemandSignalCalibrator",
    "coverage_inside_band",
]
