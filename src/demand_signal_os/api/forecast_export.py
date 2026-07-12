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
