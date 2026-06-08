"""ForecastFallbackStrategy tests."""

from __future__ import annotations

import pytest

from demand_signal_os.forecasting.fallback import (
    ForecastUnavailable,
    apply_fallback,
)
from demand_signal_os.ops_schemas import ForecastFallbackStrategy


def test_reject_raises_forecast_unavailable() -> None:
    strategy = ForecastFallbackStrategy(strategy_type="cold_start", fallback="reject")
    with pytest.raises(ForecastUnavailable) as exc:
        apply_fallback(strategy, reason="no history")
    assert exc.value.strategy is strategy
    assert "no history" in str(exc.value)


def test_non_reject_raises_not_implemented_in_v0_1() -> None:
    strategy = ForecastFallbackStrategy(
        strategy_type="cold_start", fallback="family_aggregate_prior"
    )
    with pytest.raises(NotImplementedError) as exc:
        apply_fallback(strategy)
    assert "v0.1" in str(exc.value)


def test_forecast_unavailable_carries_strategy_for_observability() -> None:
    strategy = ForecastFallbackStrategy(strategy_type="discontinued", fallback="reject")
    try:
        apply_fallback(strategy, reason="last 6 months are all zero")
    except ForecastUnavailable as err:
        assert err.strategy.strategy_type == "discontinued"
        assert "discontinued" in str(err)
        return
    pytest.fail("ForecastUnavailable not raised")
