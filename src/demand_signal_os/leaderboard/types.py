"""Leaderboard contract types.

The leaderboard is an ML-capability layer *inside* the Enterprise e2e bundle
(PlanningOS -> DSO -> SimOS -> O2C ~ Plan2Cash), NOT a standalone AutoML
product. It absorbs the "compare-and-pick" UX of tools like PyCaret while
keeping DSO's differentiators: probabilistic ranking (CRPS + interval
coverage), a beats-naive credibility gate, deterministic reproducibility,
and a winner that emits a bundle-ready ``ForecastBundle`` the downstream
engines already consume.

Per CONSTITUTION §8 (library-first) + §9 (reproducibility): every field that
feeds ranking is a pure function of (data, config, seed). ``data_cut_timestamp``
is INJECTED here rather than read from the wall clock so reruns are
byte-identical (RULE 5).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Canonical quantile band shared across the engine (mirrors
# forecasting.gbm.CANONICAL_QUANTILES and protocol.quantiles_from_samples).
CANONICAL_QUANTILES: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)

IntermittentMode = Literal["auto", "on", "off"]
HorizonLabel = Literal["operational", "tactical", "strategic"]
# Forecaster-set selector — lets a user focus the panel (and cut runtime).
# "all"/"full" run the whole panel; the rest narrow to a class. The 3 naive
# benchmarks ALWAYS run regardless (the beats-naive gate). For full control,
# pass an explicit ``methods`` allowlist (takes precedence over the class).
ForecasterSet = Literal["all", "full", "statistical", "ml", "intermittent", "fast"]


class LeaderboardConfig(BaseModel):
    """The bounded knobs a user can turn — deliberately NOT an AutoML search.

    Only four user-facing knobs (horizon, season_length, quantile_levels,
    intermittent_mode); everything else (lags, MLE alpha, rolling windows)
    stays engine-controlled and provenance-stamped. This keeps the surface
    a capability layer, not a hyperparameter-search competitor.
    """

    sku_id: str
    location_id: str
    horizon: int = Field(ge=1, description="buckets ahead per backtest window")
    season_length: int = Field(default=12, ge=1)
    quantile_levels: list[float] = Field(default_factory=lambda: list(CANONICAL_QUANTILES))
    intermittent_mode: IntermittentMode = "auto"
    # Panel focus (default "all" = current behaviour). When a class is chosen,
    # only that class competes; intermittent_mode is consulted only for
    # "all"/"full". ``methods`` (explicit allowlist) overrides this when set.
    forecaster_set: ForecasterSet = "all"
    methods: list[str] | None = None
    seed: int = 42
    n_windows: int = Field(default=4, ge=1)
    min_train_size: int = Field(default=24, ge=1)
    horizon_label: HorizonLabel = "operational"
    data_cut_timestamp: datetime
    min_quantile_spread: float | None = Field(default=None, ge=0.0)

    @field_validator("quantile_levels")
    @classmethod
    def _levels_must_be_canonical(cls, v: list[float]) -> list[float]:
        unknown = [q for q in v if q not in CANONICAL_QUANTILES]
        if unknown:
            raise ValueError(
                f"quantile_levels must be a subset of {CANONICAL_QUANTILES}; "
                f"got unknown {unknown}"
            )
        if not v:
            raise ValueError("quantile_levels must not be empty")
        return v


class LeaderboardEntry(BaseModel):
    """One method's row on the leaderboard."""

    method_id: str
    rank: int
    is_benchmark: bool
    n_windows: int
    crps: float
    smape: float | None
    pinball_q50: float
    pinball_q90: float
    wis: float
    coverage_50: float | None
    coverage_90: float | None
    # None for benchmarks (they ARE the gate); bool for forecasters.
    beats_all_benchmarks: bool | None


class LeaderboardResult(BaseModel):
    """Ranked leaderboard + the trustworthy winner recommendation.

    ``content_hash`` is a deterministic digest of the ranked metrics
    (rounded), used by the trust-gate receipt to certify reproducibility.
    """

    config: LeaderboardConfig
    entries: list[LeaderboardEntry]
    winner_method_id: str
    winner_is_benchmark: bool
    feature_set_hash: str
    n_methods: int
    content_hash: str
