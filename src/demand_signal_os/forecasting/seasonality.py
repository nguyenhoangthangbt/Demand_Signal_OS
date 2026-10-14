"""Season-length detection and quick-forecast settings resolution.

The quick (single-series) forecast used to hardcode ``season_length=7`` and
``method_id="ets"``. A monthly series with a Q4 peak then forecast flat,
because a 7-period cycle does not exist in monthly data (audit finding C-05).

This module infers the repeating cycle from the numbers themselves and picks a
method that can actually fit that cycle with the history available:

* ``detect_season_length`` scores a small set of practitioner cycle lengths
  (4, 7, 12, 13, 52) by the lag correlation of the linearly detrended series
  and keeps the strongest one that clears a significance floor. A candidate
  needs two full cycles of history to be scored at all.
* ``resolve_forecast_settings`` turns ``"auto"`` season / method requests into
  concrete values and says where each came from, so the UI can show "detected
  a 12-period cycle" rather than silently changing the model.

Pure numpy plus one deterministic AutoETS fit: same history in, same settings
out (CLAUDE.md RULE 5). No RNG is used here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

# Cycle lengths a supply-chain planner meets in practice:
#   4  = quarterly pattern in monthly data / monthly pattern in weekly data
#   7  = day-of-week pattern in daily data
#   12 = yearly pattern in monthly data
#   13 = quarterly pattern in weekly data
#   52 = yearly pattern in weekly data
SEASON_CANDIDATES: tuple[int, ...] = (4, 7, 12, 13, 52)

# A lag correlation must clear BOTH floors to count as a real cycle: an
# absolute floor (a weak wiggle is not worth a seasonal model) and the usual
# 2/sqrt(pairs) significance band for an autocorrelation estimate.
_MIN_STRENGTH = 0.5

# What each cycle usually means, for plain-language notes in the UI.
SEASON_MEANING: dict[int, str] = {
    4: "a 4-period cycle (quarterly in monthly data, or monthly in weekly data)",
    7: "a 7-period cycle (a weekly pattern in daily data)",
    12: "a 12-period cycle (a yearly pattern in monthly data)",
    13: "a 13-period cycle (a quarterly pattern in weekly data)",
    52: "a 52-period cycle (a yearly pattern in weekly data)",
}


@dataclass(frozen=True)
class SeasonDetection:
    """Result of :func:`detect_season_length`.

    ``season_length`` is 1 when no cycle cleared the floor (non-seasonal).
    ``scores`` maps every candidate that had two full cycles of history to
    its detrended lag correlation (rounded, for display and audit).
    """

    season_length: int
    strength: float | None
    scores: dict[int, float] = field(default_factory=dict)


def _lag_correlation(residual: np.ndarray, lag: int) -> float:
    """Pearson correlation between the series and itself ``lag`` steps later."""
    a = residual[:-lag]
    b = residual[lag:]
    sa = float(np.std(a))
    sb = float(np.std(b))
    if sa == 0.0 or sb == 0.0:
        return 0.0
    return float(np.mean((a - a.mean()) * (b - b.mean())) / (sa * sb))


def detect_season_length(
    history: list[float], candidates: tuple[int, ...] = SEASON_CANDIDATES
) -> SeasonDetection:
    """Infer the repeating cycle length of ``history`` (1 = no cycle).

    The series is linearly detrended first so a steady growth trend does not
    masquerade as a cycle. A candidate is scored only when the history holds
    at least two full cycles of it. The winner is the highest-scoring
    candidate whose correlation clears ``max(0.5, 2/sqrt(pairs))``; ties go to
    the candidate listed first.
    """
    y = np.asarray(history, dtype=float)
    n = int(y.size)
    if n < 2 * min(candidates) or not np.all(np.isfinite(y)):
        return SeasonDetection(season_length=1, strength=None)
    t = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(t, y, 1)
    residual = y - (slope * t + intercept)
    # A flat (or perfectly linear) series leaves only float round-off behind;
    # correlating round-off would "find" any cycle, so treat it as no cycle.
    scale = max(1.0, float(np.mean(np.abs(y))))
    if float(np.std(residual)) <= 1e-9 * scale:
        return SeasonDetection(season_length=1, strength=None)

    scores: dict[int, float] = {}
    best_m, best_r = 1, None
    for m in candidates:
        if n < 2 * m:
            continue
        r = _lag_correlation(residual, m)
        scores[m] = round(r, 4)
        floor = max(_MIN_STRENGTH, 2.0 / float(np.sqrt(n - m)))
        if r >= floor and (best_r is None or r > best_r):
            best_m, best_r = m, r
    return SeasonDetection(
        season_length=best_m,
        strength=None if best_r is None else round(best_r, 4),
        scores=scores,
    )


def ets_fits_season(history: list[float], season_length: int) -> bool:
    """True when AutoETS selects a seasonal model at ``season_length``.

    AutoETS silently drops the seasonal component when the history is too
    short or too irregular for it; the forecast then comes out flat even
    though a cycle exists. This lets the caller fall back to a method that
    can carry the cycle (CES) instead.
    """
    if season_length <= 1:
        return False
    from statsforecast.models import AutoETS

    try:
        fitted = AutoETS(season_length=season_length).fit(np.asarray(history, dtype=float))
    except Exception:  # noqa: BLE001 - an unfittable series simply has no ETS season
        return False
    method = str(getattr(fitted, "model_", {}).get("method", ""))
    # "ETS(E,T,S)": the third component is the seasonal one; "N" = none.
    inner = method[method.find("(") + 1 : method.rfind(")")]
    parts = [p.strip() for p in inner.split(",")]
    return len(parts) == 3 and parts[2] != "N"


@dataclass(frozen=True)
class ForecastSettings:
    """Concrete settings for one quick forecast plus where they came from."""

    season_length: int
    season_source: Literal["detected", "given"]
    method_id: str
    method_source: Literal["auto", "given"]
    season_strength: float | None
    note: str

    def as_dict(self) -> dict[str, object]:
        return {
            "season_length": self.season_length,
            "season_source": self.season_source,
            "season_strength": self.season_strength,
            "method_id": self.method_id,
            "method_source": self.method_source,
            "note": self.note,
        }


def resolve_forecast_settings(
    history: list[float],
    season_length: int | Literal["auto"],
    method_id: str,
) -> ForecastSettings:
    """Turn ``"auto"`` season / method into concrete values, with a note.

    * ``season_length="auto"`` -> :func:`detect_season_length`.
    * ``method_id="auto"`` -> ETS, unless a cycle is in play and ETS cannot fit
      it from this history, in which case CES (complex exponential smoothing),
      which can fit a seasonal pattern from two cycles.

    Explicit values pass through untouched, so existing callers that send a
    number and a method get exactly the forecast they got before.
    """
    strength: float | None = None
    if season_length == "auto":
        det = detect_season_length(history)
        m = det.season_length
        strength = det.strength
        season_source: Literal["detected", "given"] = "detected"
    else:
        m = int(season_length)
        season_source = "given"

    notes: list[str] = []
    if season_source == "detected":
        if m > 1:
            notes.append(f"Detected {SEASON_MEANING.get(m, f'a {m}-period cycle')}.")
        else:
            notes.append("No repeating cycle detected, so the forecast is non-seasonal.")

    if method_id == "auto":
        method_source: Literal["auto", "given"] = "auto"
        if m > 1 and not ets_fits_season(history, m):
            resolved_method = "ces"
            notes.append(
                "ETS could not fit that cycle from this much history, so CES "
                "(complex exponential smoothing) carries it instead."
            )
        else:
            resolved_method = "ets"
    else:
        method_source = "given"
        resolved_method = method_id

    if m > 1 and len(history) < 3 * m:
        notes.append(
            f"With fewer than three full cycles ({len(history)} periods for a "
            f"{m}-period cycle) the band likely understates the real "
            "uncertainty. Run the leaderboard to check its coverage."
        )

    return ForecastSettings(
        season_length=m,
        season_source=season_source,
        method_id=resolved_method,
        method_source=method_source,
        season_strength=strength,
        note=" ".join(notes),
    )


__all__ = [
    "SEASON_CANDIDATES",
    "SEASON_MEANING",
    "ForecastSettings",
    "SeasonDetection",
    "detect_season_length",
    "ets_fits_season",
    "resolve_forecast_settings",
]
