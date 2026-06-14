"""Leaderboard orchestrator — run every selected method through the existing
walk-forward harness, rank probabilistically, apply the beats-naive gate, and
recommend the trustworthy winner.

This is the composition layer; it adds NO new modeling. It reuses
``backtest.harness`` (windows, scoring, benchmark gate) verbatim, with one
determinism fix: the harness stamps ``data_cut_timestamp`` from the wall
clock (``harness.make_windows`` -> ``datetime.now``), which would break
byte-identical reruns. We override every window's timestamp with the
config-injected ``data_cut_timestamp`` so the leaderboard is reproducible
(RULE 5).

The winner emits a bundle-ready forecast for the downstream Enterprise bundle
(PlanningOS / SimOS / O2C ~ Plan2Cash) via the existing consumers; selecting
the winner here is the enrichment seam, not a new product.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import numpy as np

from demand_signal_os.backtest.harness import (
    BacktestSummary,
    evaluate_window,
    make_windows,
    mark_benchmark_beating,
    summarize,
)
from demand_signal_os.forecasting.registry import (
    BENCHMARK_IDS,
    build_method,
    select_method_ids,
)
from demand_signal_os.leaderboard.types import (
    LeaderboardConfig,
    LeaderboardEntry,
    LeaderboardResult,
)
from demand_signal_os.forecasting.protocol import ForecastRequest
from demand_signal_os.ops_schemas import DemandActual, ForecastBundle, TimeBucket

_HASH_PRECISION = 6  # decimals retained in the reproducibility digest


def _feature_set_hash(history: list[float]) -> str:
    """Deterministic digest of the input series (matches method provenance)."""
    arr = np.asarray(history, dtype=float)
    return hashlib.sha256(arr.tobytes()).hexdigest()[:16]


def _entry_from_summary(
    summary: BacktestSummary, *, is_benchmark: bool
) -> LeaderboardEntry:
    return LeaderboardEntry(
        method_id=summary.method_id,
        rank=0,  # assigned after sorting
        is_benchmark=is_benchmark,
        n_windows=summary.n_windows,
        crps=summary.mean_crps,
        smape=summary.mean_smape,
        pinball_q50=summary.mean_pinball_q50,
        pinball_q90=summary.mean_pinball_q90,
        wis=summary.mean_wis,
        coverage_50=summary.coverage_50,
        coverage_90=summary.coverage_90,
        beats_all_benchmarks=None if is_benchmark else summary.beats_all_benchmarks,
    )


def _content_hash(entries: list[LeaderboardEntry]) -> str:
    """Digest the ranked, rounded metrics — the reproducibility certificate.

    Excludes non-deterministic bundle metadata (uuid bundle ids, produced_at
    wall-clock) by construction: only ranked metric values are hashed.
    """
    payload = [
        [
            e.rank,
            e.method_id,
            round(e.crps, _HASH_PRECISION),
            round(e.wis, _HASH_PRECISION),
            e.beats_all_benchmarks,
        ]
        for e in entries
    ]
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _select_winner(entries: list[LeaderboardEntry]) -> tuple[str, bool]:
    """Trustworthy winner: best forecaster that beats ALL benchmarks; else
    fall back to the best benchmark (CONSTITUTION §5 — never ship a model
    that can't beat naive). ``entries`` must already be CRPS-ranked.
    """
    for e in entries:  # ranked ascending by CRPS
        if not e.is_benchmark and e.beats_all_benchmarks:
            return e.method_id, False
    # No forecaster cleared the gate -> recommend the best benchmark.
    for e in entries:
        if e.is_benchmark:
            return e.method_id, True
    # Degenerate (no benchmarks ran) -> best overall.
    return entries[0].method_id, entries[0].is_benchmark


def orchestrate(
    actuals: list[DemandActual], config: LeaderboardConfig
) -> LeaderboardResult:
    """Run the full leaderboard for one (sku, location) series.

    Deterministic in (actuals, config): same inputs -> identical ranking and
    ``content_hash``.
    """
    history = [r.units_sold for r in actuals]

    windows = make_windows(
        history_length=len(history),
        n_windows=config.n_windows,
        horizon_size=config.horizon,
        min_train_size=config.min_train_size,
    )
    # Determinism fix: replace wall-clock cut with the injected timestamp.
    windows = [replace(w, data_cut_timestamp=config.data_cut_timestamp) for w in windows]

    method_ids = select_method_ids(history, config)

    summaries: dict[str, BacktestSummary] = {}
    for method_id in method_ids:
        method = build_method(method_id, config)
        window_results = []
        for window in windows:
            window_results.extend(
                evaluate_window(
                    method,
                    actuals,
                    history,
                    window,
                    horizon_label=config.horizon_label,
                    seed=config.seed,
                )
            )
        summaries[method_id] = summarize(window_results)

    benchmark_summaries = [summaries[b] for b in BENCHMARK_IDS if b in summaries]

    entries: list[LeaderboardEntry] = []
    for method_id, summary in summaries.items():
        is_benchmark = method_id in BENCHMARK_IDS
        if not is_benchmark:
            summary = mark_benchmark_beating(summary, benchmark_summaries)
        entries.append(_entry_from_summary(summary, is_benchmark=is_benchmark))

    # Rank by CRPS ascending; method_id tie-break keeps order deterministic.
    entries.sort(key=lambda e: (round(e.crps, _HASH_PRECISION), e.method_id))
    for i, entry in enumerate(entries):
        entry.rank = i + 1

    winner_method_id, winner_is_benchmark = _select_winner(entries)

    return LeaderboardResult(
        config=config,
        entries=entries,
        winner_method_id=winner_method_id,
        winner_is_benchmark=winner_is_benchmark,
        feature_set_hash=_feature_set_hash(history),
        n_methods=len(entries),
        content_hash=_content_hash(entries),
    )


def _next_buckets(last: TimeBucket, horizon: int) -> list[TimeBucket]:
    """Extend the series cadence forward by ``horizon`` buckets."""
    delta = last.end - last.start
    buckets: list[TimeBucket] = []
    start = last.end
    for _ in range(horizon):
        end = start + delta
        buckets.append(TimeBucket(period=last.period, start=start, end=end))
        start = end
    return buckets


def fit_winner_bundle(
    actuals: list[DemandActual], config: LeaderboardConfig, winner_method_id: str
) -> ForecastBundle:
    """Fit the winning method on the FULL history and emit a bundle-ready
    ``ForecastBundle`` for the downstream e2e engines (PlanningOS / SimOS /
    O2C). This is the enrichment hand-off: the leaderboard picks, this ships.
    """
    method = build_method(winner_method_id, config)
    history = [r.units_sold for r in actuals]
    horizon_buckets = _next_buckets(actuals[-1].bucket, config.horizon)
    request = ForecastRequest(
        sku_id=config.sku_id,
        location_id=config.location_id,
        history=history,
        history_buckets=[r.bucket for r in actuals],
        horizon_buckets=horizon_buckets,
        horizon_label=config.horizon_label,
        seed=config.seed,
        data_cut_timestamp=config.data_cut_timestamp,
    )
    return method.fit_predict(request)
