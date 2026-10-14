"""Season detection + quick-forecast settings (audit finding C-05).

Regression: the quick forecast hardcoded season 7 + ETS, so a monthly series
with a Q4 peak (the persona's real 24-month series) forecast flat at ~2,075.
These tests pin that the cycle is now inferred from the data and that the
resolved settings are deterministic (RULE 5).
"""

from __future__ import annotations

import math

import numpy as np

from demand_signal_os.forecasting.seasonality import (
    detect_season_length,
    ets_fits_season,
    resolve_forecast_settings,
)

# The exact 24-month series persona C (Marco) pasted on 2026-10-12
# (journeys/C_premium_planner/downloads/dso_dso_forecast.csv): Q4 peak.
MARCO_MONTHLY = [
    980, 940, 1050, 1100, 1180, 1120, 1060, 1090, 1250, 1420, 1780, 1950,
    1040, 990, 1110, 1170, 1240, 1190, 1130, 1160, 1330, 1510, 1890, 2080,
]
DAILY_WEEKLY_CYCLE = [10 + 3 * math.sin(2 * math.pi * i / 7) + (i % 3) for i in range(48)]
PREVIEW_SAMPLE = [42, 48, 55, 51, 58, 67, 73, 71, 65, 60, 68, 72]


def test_monthly_q4_peak_detects_yearly_cycle() -> None:
    det = detect_season_length(MARCO_MONTHLY)
    assert det.season_length == 12
    assert det.strength is not None and det.strength > 0.9


def test_daily_series_detects_weekly_cycle() -> None:
    assert detect_season_length(DAILY_WEEKLY_CYCLE).season_length == 7


def test_white_noise_is_non_seasonal() -> None:
    rng = np.random.default_rng(3)
    noise = list(100 + rng.normal(0, 10, 60))
    assert detect_season_length(noise).season_length == 1


def test_short_or_flat_series_is_non_seasonal() -> None:
    assert detect_season_length(PREVIEW_SAMPLE).season_length == 1
    assert detect_season_length([5.0] * 30).season_length == 1
    assert detect_season_length([1.0, 2.0, 3.0]).season_length == 1


def test_candidate_needs_two_full_cycles() -> None:
    det = detect_season_length(MARCO_MONTHLY[:23])  # < 2 x 12
    assert 12 not in det.scores


def test_auto_settings_for_marco_are_seasonal_and_explained() -> None:
    s = resolve_forecast_settings(MARCO_MONTHLY, "auto", "auto")
    assert s.season_length == 12 and s.season_source == "detected"
    assert s.method_id in {"ets", "ces"} and s.method_source == "auto"
    assert "12-period cycle" in s.note
    # Two cycles only: the note must warn the band is optimistic.
    assert "understates" in s.note


def test_explicit_values_pass_through_untouched() -> None:
    s = resolve_forecast_settings(MARCO_MONTHLY, 7, "ets")
    assert (s.season_length, s.method_id) == (7, "ets")
    assert (s.season_source, s.method_source) == ("given", "given")
    assert s.note == ""


def test_ets_fits_season_reports_seasonal_component() -> None:
    assert ets_fits_season(MARCO_MONTHLY, 12) is True
    assert ets_fits_season(MARCO_MONTHLY, 1) is False


def test_resolution_is_deterministic() -> None:
    a = resolve_forecast_settings(MARCO_MONTHLY, "auto", "auto")
    b = resolve_forecast_settings(MARCO_MONTHLY, "auto", "auto")
    assert a == b
