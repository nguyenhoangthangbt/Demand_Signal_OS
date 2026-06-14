"""Orchestrator tests — ranking, gate, winner, coverage."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from demand_signal_os.backtest.synthetic import SyntheticConfig, generate
from demand_signal_os.forecasting.registry import BENCHMARK_IDS
from demand_signal_os.leaderboard import LeaderboardConfig, orchestrate

_CUT = datetime(2026, 1, 1, tzinfo=UTC)


def _series(**kw: object):
    cfg = SyntheticConfig(n_buckets=80, noise_std=1.5, season_length=7, **kw)
    return generate("SKU-1", "DC-1", cfg, seed=42)


def _cfg(**kw: object) -> LeaderboardConfig:
    base: dict[str, object] = dict(
        sku_id="SKU-1", location_id="DC-1", horizon=10, season_length=7,
        n_windows=4, min_train_size=40, intermittent_mode="off",
        data_cut_timestamp=_CUT,
    )
    base.update(kw)
    return LeaderboardConfig(**base)  # type: ignore[arg-type]


def test_orchestrate_ranks_all_selected_methods() -> None:
    result = orchestrate(_series(), _cfg())
    # off-mode: ets, gbm, arima, theta, ces + 3 benchmarks = 8
    assert result.n_methods == 8
    assert {e.method_id for e in result.entries} == {
        "ets", "gbm", "arima", "theta", "ces", *BENCHMARK_IDS,
    }


def test_ranks_are_contiguous_and_crps_sorted() -> None:
    result = orchestrate(_series(), _cfg())
    ranks = [e.rank for e in result.entries]
    assert ranks == list(range(1, len(ranks) + 1))
    crps_in_rank_order = [e.crps for e in result.entries]
    assert crps_in_rank_order == sorted(crps_in_rank_order)


def test_benchmarks_have_no_beat_flag_forecasters_do() -> None:
    result = orchestrate(_series(), _cfg())
    for e in result.entries:
        if e.is_benchmark:
            assert e.beats_all_benchmarks is None
        else:
            assert e.beats_all_benchmarks in (True, False)


def test_coverage_is_populated_and_in_unit_range() -> None:
    result = orchestrate(_series(), _cfg())
    for e in result.entries:
        assert e.coverage_50 is not None and 0.0 <= e.coverage_50 <= 1.0
        assert e.coverage_90 is not None and 0.0 <= e.coverage_90 <= 1.0


def test_winner_beats_benchmarks_or_falls_back_to_benchmark() -> None:
    result = orchestrate(_series(), _cfg())
    winner = next(e for e in result.entries if e.method_id == result.winner_method_id)
    if result.winner_is_benchmark:
        assert winner.is_benchmark
        # Fallback only happens when NO forecaster cleared the gate.
        assert all(
            not e.beats_all_benchmarks for e in result.entries if not e.is_benchmark
        )
    else:
        assert not winner.is_benchmark
        assert winner.beats_all_benchmarks is True


def test_intermittent_auto_expands_panel_on_sparse_series() -> None:
    result = orchestrate(
        _series(intermittency_rate=0.5), _cfg(intermittent_mode="auto")
    )
    # ets, gbm, arima, theta, ces + 3 intermittent + 3 benchmarks = 11
    assert result.n_methods == 11


def test_quantile_levels_reject_non_canonical() -> None:
    with pytest.raises(ValueError):
        _cfg(quantile_levels=[0.5, 0.42])
