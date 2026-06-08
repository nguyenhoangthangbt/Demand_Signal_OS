"""Walk-forward harness tests — verifies M5-aligned protocol."""

from __future__ import annotations

import pytest

from demand_signal_os.backtest.benchmarks import (
    MovingAverageMethod,
    NaiveSeasonalMethod,
    SESMethod,
)
from demand_signal_os.backtest.harness import (
    evaluate_window,
    make_windows,
    mark_benchmark_beating,
    summarize,
)
from demand_signal_os.backtest.synthetic import SyntheticConfig, generate, history_values


def test_make_windows_four_non_overlapping() -> None:
    windows = make_windows(history_length=100, n_windows=4, horizon_size=10,
                            min_train_size=30)
    assert len(windows) == 4
    # Chronological order
    assert windows[0].train_size < windows[-1].train_size
    # Non-overlapping horizons
    for i in range(len(windows) - 1):
        assert windows[i + 1].train_size == windows[i].train_size + 10


def test_make_windows_caps_at_min_train_size() -> None:
    """If history is too short for n_windows, fewer windows are returned."""
    windows = make_windows(history_length=50, n_windows=4, horizon_size=10,
                            min_train_size=30)
    # 50 - 10 = 40 last train_end; step back 10 each => 40, 30, 20 (below min)
    assert len(windows) == 2


def test_make_windows_raises_when_history_too_short() -> None:
    with pytest.raises(ValueError):
        make_windows(history_length=20, n_windows=4, horizon_size=10, min_train_size=30)


def test_evaluate_window_against_naive_seasonal() -> None:
    """End-to-end: synthetic → window → evaluate → metrics defined."""
    cfg = SyntheticConfig(n_buckets=80, noise_std=0.5, censoring_rate=0.0)
    actuals = generate("SKU-1", "DC-1", cfg, seed=42)
    hist = history_values(actuals)
    windows = make_windows(history_length=80, n_windows=2, horizon_size=10,
                            min_train_size=40)
    method = NaiveSeasonalMethod(season_length=7)
    results = evaluate_window(method, actuals, hist, windows[0])
    assert len(results) == 10
    assert all(r.method_id == "naive_seasonal" for r in results)
    assert all(r.crps >= 0 for r in results)


def test_summarize_aggregates_across_windows() -> None:
    cfg = SyntheticConfig(n_buckets=80, noise_std=0.5)
    actuals = generate("SKU-1", "DC-1", cfg, seed=42)
    hist = history_values(actuals)
    windows = make_windows(history_length=80, n_windows=2, horizon_size=10,
                            min_train_size=40)
    method = NaiveSeasonalMethod(season_length=7)
    all_results = []
    for w in windows:
        all_results.extend(evaluate_window(method, actuals, hist, w))
    summary = summarize(all_results)
    assert summary.method_id == "naive_seasonal"
    assert summary.n_windows == 2
    assert summary.mean_crps >= 0


def test_summarize_rejects_mixed_methods() -> None:
    cfg = SyntheticConfig(n_buckets=80, noise_std=0.5)
    actuals = generate("SKU-1", "DC-1", cfg, seed=42)
    hist = history_values(actuals)
    windows = make_windows(history_length=80, n_windows=1, horizon_size=10,
                            min_train_size=40)
    naive = NaiveSeasonalMethod(season_length=7)
    ma = MovingAverageMethod(window=4)
    mixed = (
        evaluate_window(naive, actuals, hist, windows[0])
        + evaluate_window(ma, actuals, hist, windows[0])
    )
    with pytest.raises(ValueError):
        summarize(mixed)


def test_mark_benchmark_beating() -> None:
    """A candidate beating all benchmarks gets flagged."""
    cfg = SyntheticConfig(n_buckets=80, noise_std=0.5)
    actuals = generate("SKU-1", "DC-1", cfg, seed=42)
    hist = history_values(actuals)
    windows = make_windows(history_length=80, n_windows=2, horizon_size=10,
                            min_train_size=40)

    methods = [
        NaiveSeasonalMethod(season_length=7),
        SESMethod(alpha=0.3),
        MovingAverageMethod(window=4),
    ]
    summaries = []
    for m in methods:
        rs = []
        for w in windows:
            rs.extend(evaluate_window(m, actuals, hist, w))
        summaries.append(summarize(rs))

    # Mark each against the other two as "benchmarks"
    for i, candidate in enumerate(summaries):
        others = [s for j, s in enumerate(summaries) if j != i]
        marked = mark_benchmark_beating(candidate, others)
        assert marked.beats_all_benchmarks is not None
