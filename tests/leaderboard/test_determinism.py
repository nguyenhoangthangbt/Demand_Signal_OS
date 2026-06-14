"""Deterministic baseline (RULE 5) — same inputs => byte-identical ranking.

Two layers:
1. Run-twice identity: the full leaderboard (incl. ETS/GBM) must produce an
   identical content_hash and identical CRPS on repeat — catches any
   non-determinism creeping into the math path.
2. Hardcoded baseline: the pure-numpy benchmark CRPS values are byte-stable
   and pinned here; drift means a non-deterministic component landed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from demand_signal_os.backtest.synthetic import SyntheticConfig, generate
from demand_signal_os.leaderboard import LeaderboardConfig, orchestrate

_CUT = datetime(2026, 1, 1, tzinfo=UTC)


def _series():
    cfg = SyntheticConfig(n_buckets=80, noise_std=1.5, season_length=7)
    return generate("SKU-1", "DC-1", cfg, seed=42)


def _cfg() -> LeaderboardConfig:
    return LeaderboardConfig(
        sku_id="SKU-1", location_id="DC-1", horizon=10, season_length=7,
        n_windows=4, min_train_size=40, intermittent_mode="off", seed=42,
        data_cut_timestamp=_CUT,
    )


def test_run_twice_identical_content_hash() -> None:
    a = orchestrate(_series(), _cfg())
    b = orchestrate(_series(), _cfg())
    assert a.content_hash == b.content_hash
    assert [e.method_id for e in a.entries] == [e.method_id for e in b.entries]
    assert [e.crps for e in a.entries] == [e.crps for e in b.entries]


def test_run_twice_identical_winner() -> None:
    a = orchestrate(_series(), _cfg())
    b = orchestrate(_series(), _cfg())
    assert a.winner_method_id == b.winner_method_id
    assert a.winner_is_benchmark == b.winner_is_benchmark


def test_feature_set_hash_stable() -> None:
    a = orchestrate(_series(), _cfg())
    b = orchestrate(_series(), _cfg())
    assert a.feature_set_hash == b.feature_set_hash


# --- Hardcoded baseline (filled from first observed run) ---------------------
# Pinned benchmark CRPS (pure-numpy, byte-stable cross-machine). DRIFT = a
# non-deterministic component crept into the benchmark path.
_BASELINE_BENCHMARK_CRPS: dict[str, float] = {
    "naive_seasonal": 1.368578772053893,
    "ses": 1.5478209647309407,
    "moving_average": 2.1867098744678595,
}
# Structural baseline: ETS is the trustworthy winner (beats all benchmarks).
_BASELINE_WINNER = "ets"


def test_benchmark_crps_baseline() -> None:
    """Pinned byte-stable benchmark CRPS (pure-numpy path)."""
    result = orchestrate(_series(), _cfg())
    observed = {e.method_id: e.crps for e in result.entries if e.is_benchmark}
    for method_id, expected in _BASELINE_BENCHMARK_CRPS.items():
        assert observed[method_id] == expected, (
            f"{method_id} CRPS drifted: {observed[method_id]} != {expected}"
        )


def test_winner_baseline() -> None:
    """Winner recommendation is stable and clears the benchmark gate."""
    result = orchestrate(_series(), _cfg())
    assert result.winner_method_id == _BASELINE_WINNER
    assert result.winner_is_benchmark is False
