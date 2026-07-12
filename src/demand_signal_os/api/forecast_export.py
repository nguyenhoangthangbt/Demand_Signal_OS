"""Forecast result -> .xlsx exporter.

Turns the ``/forecast/single`` response (a real ``ForecastBundle`` + optional
widening band + the posted history) into a native Excel workbook, so the
customer can open the terminal quantiles, the per-step band, and the provenance
in the tool they validate in — the .xlsx peer of the client-side CSV download.

All xlsx assembly is delegated to ``excel_io.tables_to_xlsx``; this module only
maps the bundle's JSON shape into ``(name, headers, rows)`` sheets. Shape-tolerant:
missing sections (no band, thin provenance) simply produce fewer rows.
"""
from __future__ import annotations

from typing import Any

from excel_io import tables_to_xlsx

_QUANTILE_KEYS = ("q05", "q10", "q25", "q50", "q75", "q90", "q95")


def forecast_to_xlsx(result: dict[str, Any], history: list[float]) -> bytes:
    """Build the forecast workbook (.xlsx bytes) from a ``/forecast/single``
    response dict (``{"method", "bundle", optional "band", "band_truncated"}``)
    plus the posted ``history``."""
    bundle = result.get("bundle") or {}
    method = result.get("method") or bundle.get("method") or "forecast"
    quantiles = bundle.get("quantiles") or {}

    sheets: list[tuple[str, list[str], list[list[Any]]]] = []

    # 1) Forecast — terminal-horizon quantiles + mean (the headline band).
    q_rows: list[list[Any]] = [
        [k, quantiles[k]] for k in _QUANTILE_KEYS if quantiles.get(k) is not None
    ]
    if bundle.get("mean") is not None:
        q_rows.append(["mean", bundle["mean"]])
    if q_rows:
        sheets.append(("Forecast", ["Quantile", "Value"], q_rows))

    # 2) Band — per-step widening quantiles (h = 1..horizon), if requested.
    band = result.get("band")
    if isinstance(band, list) and band:
        headers: list[str] = []
        for step in band:
            for k in step.keys():
                if k not in headers:
                    headers.append(k)
        rows = [[step.get(h) for h in headers] for step in band]
        sheets.append(("Band", headers, rows))

    # 3) History — the posted series, so every quantile is re-derivable.
    if history:
        sheets.append(("History", ["t", "value"],
                       [[i, v] for i, v in enumerate(history)]))

    # 4) Provenance — method, model, seed, hashes, distribution, freshness.
    prov = bundle.get("provenance") or {}
    dist = bundle.get("distribution") or {}
    bucket = bundle.get("bucket") or {}
    p_rows: list[list[Any]] = [
        ["method", method],
        ["sku_id", bundle.get("sku_id")],
        ["location_id", bundle.get("location_id")],
        ["horizon_label", bundle.get("horizon_label")],
        ["bucket_period", bucket.get("period")],
        ["fallback_applied", bundle.get("fallback_applied")],
        ["distribution_family", dist.get("family")],
    ]
    for pk, pv in (dist.get("params") or {}).items():
        p_rows.append([f"distribution.{pk}", pv])
    for pk in ("forecast_bundle_id", "model_id", "commit_sha", "seed",
               "feature_set_hash", "data_cut_timestamp", "produced_at"):
        if prov.get(pk) is not None:
            p_rows.append([pk, prov[pk]])
    if result.get("band_truncated"):
        p_rows.append(["band_truncated", True])
    p_rows = [r for r in p_rows if r[1] is not None]
    if p_rows:
        sheets.append(("Provenance", ["Field", "Value"], p_rows))

    if not sheets:
        sheets.append(("Forecast", ["Note"], [["forecast produced no exportable band"]]))

    return tables_to_xlsx(
        sheets,
        workbook_title="DemandSignalOS forecast",
        footer=(f"DemandSignalOS {method} forecast — downloaded from "
                "demand-signal.sim-os.ai"),
    )


# Column order for the leaderboard sheet (metrics that exist on LeaderboardEntry).
_LEADERBOARD_COLS = (
    "rank", "method_id", "is_benchmark", "crps", "smape",
    "pinball_q50", "pinball_q90", "wis", "coverage_50", "coverage_90",
    "beats_all_benchmarks", "n_windows",
)


def leaderboard_to_xlsx(
    result: dict[str, Any],
    winner_forecast: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build the forecaster-leaderboard workbook (.xlsx bytes) from a
    ``LeaderboardResult`` dict — the ranked competition, the winning method's
    per-horizon forecasted values, plus the winner + reproducibility summary.

    ``winner_forecast`` is an ordered list of per-horizon quantile dicts
    (``{"h": 1, "q05": .., "q50": .., "q95": ..}``) for the winning method — the
    actual forecasted numbers over the horizon. Shape-tolerant throughout."""
    entries = result.get("entries") or []
    sheets: list[tuple[str, list[str], list[list[Any]]]] = []

    # 1) Leaderboard — one row per method, ranked (as returned).
    if entries:
        headers = [c for c in _LEADERBOARD_COLS
                   if any(c in e for e in entries)]
        rows = [[e.get(c) for c in headers] for e in entries]
        sheets.append(("Leaderboard", headers, rows))

    # 2) Winner Forecast — the winning method's forecasted values per horizon
    #    (a real widening band), so the export carries the actual numbers, not
    #    just the ranking metrics.
    if winner_forecast:
        cols: list[str] = ["h"]
        for step in winner_forecast:
            for k in step.keys():
                if k not in cols:
                    cols.append(k)
        rows = [[step.get(c) for c in cols] for step in winner_forecast]
        sheets.append(("Winner Forecast", cols, rows))

    # 3) Summary — winner + reproducibility + the run's config knobs.
    cfg = result.get("config") or {}
    summary: list[list[Any]] = [
        ["winner_method_id", result.get("winner_method_id")],
        ["winner_is_benchmark", result.get("winner_is_benchmark")],
        ["n_methods", result.get("n_methods")],
        ["content_hash", result.get("content_hash")],
        ["feature_set_hash", result.get("feature_set_hash")],
    ]
    for ck in ("sku_id", "location_id", "horizon", "horizon_label", "season_length",
               "forecaster_set", "intermittent_mode", "n_windows", "min_train_size",
               "bucket_period", "seed"):
        if cfg.get(ck) is not None:
            summary.append([f"config.{ck}", cfg[ck]])
    summary = [r for r in summary if r[1] is not None]
    if summary:
        sheets.append(("Summary", ["Field", "Value"], summary))

    if not sheets:
        sheets.append(("Leaderboard", ["Note"], [["leaderboard produced no entries"]]))

    winner = result.get("winner_method_id") or "leaderboard"
    return tables_to_xlsx(
        sheets,
        workbook_title="DemandSignalOS forecaster leaderboard",
        footer=(f"DemandSignalOS leaderboard (winner: {winner}) — downloaded from "
                "demand-signal.sim-os.ai"),
    )
