"""ForecastFallbackStrategy implementations per CONTRACTS §8.

v0.1 ships only `reject` — the engine raises ForecastUnavailable when no
fallback algorithm matches. Other strategies (family_aggregate_prior,
location_aggregate_prior, expert_judgment_override, empirical_only) are
specified in the contract and reserved for v0.1.5+ when real cold-start
cases hit dogfooding.
"""

from __future__ import annotations

from demand_signal_os.ops_schemas import ForecastFallbackStrategy


class ForecastUnavailableError(Exception):
    """Raised when the engine cannot produce a forecast and no fallback applies."""

    def __init__(self, strategy: ForecastFallbackStrategy, reason: str):
        self.strategy = strategy
        self.reason = reason
        super().__init__(f"forecast unavailable [{strategy.strategy_type}]: {reason}")


# Backward-compat alias — keep the shorter name for callers prior to the
# 2026-06-08 N818 rename.
ForecastUnavailable = ForecastUnavailableError


def apply_fallback(
    strategy: ForecastFallbackStrategy,
    *,
    reason: str = "no fallback algorithm available in v0.1",
) -> None:
    """Apply a v0.1 fallback strategy.

    v0.1 implements only `reject` — raises `ForecastUnavailableError`. All
    other fallback values are valid in the schema but raise
    NotImplementedError until v0.1.5+ implementations land. This keeps the
    contract honest: callers must explicitly handle each case, not
    silently fall back.
    """
    if strategy.fallback == "reject":
        raise ForecastUnavailableError(strategy, reason)
    raise NotImplementedError(
        f"fallback '{strategy.fallback}' not implemented in v0.1 — "
        f"use 'reject' or wait for v0.1.5+ (see CONTRACTS §8)"
    )
