"""Forecast -> SimOS arrivals YAML exporter (the DSO→SimOS contract).

The machine-handoff peer of the .xlsx export. Humans audit the workbook; SimOS
consumes THIS: a ``sources``/``arrivals.schedule`` YAML block that SimOS's
config loader ingests directly (``simulation_os.config.loader``). Reuses the
tested ``consumers.simos_arrivals_adapter`` so the rate/noise math + robustness
guards are byte-identical to the in-process integration — this is the same
contract, just serialized for download instead of wired in memory.

The per-horizon forecast (a ``forecast_path`` of ``Quantiles``) becomes one
schedule entry per step (a real widening band → widening ``noise_std``).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import yaml

_YAML_HEADER = (
    "# SimOS arrivals — generated from a DemandSignalOS forecast (DSO→SimOS contract).\n"
    "# Humans audit the .xlsx; SimOS consumes this. Splice `sources` into a SimOS\n"
    "# scenario and load via simulation_os.config.loader (ScheduleDistribution).\n"
)


def _horizon_bundles(
    winner_bundle: Any,
    path: list[Any],
    *,
    bucket_period: str,
    start_date: date,
) -> list[Any]:
    """Clone the winning bundle into one bundle per horizon step, each carrying
    that step's quantiles + a consecutive bucket, so the tested adapter can turn
    them into a widening SimOS arrival schedule."""
    from demand_signal_os.ops_schemas import TimeBucket

    step = timedelta(days=1) if bucket_period == "day" else timedelta(weeks=1)
    bundles: list[Any] = []
    for i, qs in enumerate(path):
        d = start_date + step * i
        bucket = TimeBucket(period=bucket_period, start=d, end=d + step)
        # q50 (median) is the per-step rate driver; the adapter derives noise
        # from the q25/q75 band carried on `qs`.
        bundles.append(
            winner_bundle.model_copy(
                update={"bucket": bucket, "quantiles": qs, "mean": float(qs.q50)}
            )
        )
    return bundles


# The shared list-valued arrivals contract lives in excel_io (single source of
# truth); DSO produces it and SimOS's overlay import consumes the SAME spec.
from excel_io import ARRIVAL_SCHEDULE_SHEET as _ARRIVAL_SCHEDULE_SHEET  # noqa: E402


def forecast_to_simos_arrivals_xlsx(
    winner_bundle: Any,
    path: list[Any],
    *,
    bucket_period: str = "day",
    start_date: date | None = None,
) -> bytes:
    """The DSO->SimOS arrivals contract as a list-valued xlsx (the same shape
    SimOS's excel-builder accepts). Declares ``arrivals_distribution=schedule``
    and fills the Arrival Schedule sheet with one row per horizon step
    ``(time, rate_per_hour, noise_std)`` from the forecast's widening band."""
    from excel_io import arrivals_schedule_spec, generate_xlsx
    from demand_signal_os.consumers.simos_arrivals_adapter import (
        forecast_bundles_to_simos_schedule,
    )

    base = start_date or date(2026, 1, 1)
    bundles = (
        _horizon_bundles(winner_bundle, path, bucket_period=bucket_period, start_date=base)
        if path
        else [winner_bundle]
    )
    block = forecast_bundles_to_simos_schedule(bundles)
    rows = [
        {"time": e.get("time"), "rate_per_hour": e.get("rate_per_hour"),
         "noise_std": e.get("noise_std", 0.0)}
        for e in block.get("schedule", [])
    ]
    spec = arrivals_schedule_spec()
    return generate_xlsx(
        spec,
        values={"arrivals_distribution": "schedule"},
        tabular_rows={_ARRIVAL_SCHEDULE_SHEET: rows},
    )


def forecast_to_simos_arrivals_yaml(
    winner_bundle: Any,
    path: list[Any],
    *,
    bucket_period: str = "day",
    start_date: date | None = None,
    entity_type: str = "order",
    entry_node: str = "order_intake",
) -> str:
    """Serialize a forecast into a SimOS arrivals YAML string.

    ``path`` is a ``forecast_path`` (list of ``Quantiles``, one per horizon
    step). Falls back to the single terminal ``winner_bundle`` when the path is
    empty. Returns the YAML text (with an explanatory header) — the caller
    streams it as a download.
    """
    from demand_signal_os.consumers.simos_arrivals_adapter import (
        forecast_bundles_to_simos_schedule,
    )

    base = start_date or date(2026, 1, 1)
    bundles = (
        _horizon_bundles(winner_bundle, path, bucket_period=bucket_period, start_date=base)
        if path
        else [winner_bundle]
    )
    arrivals_block = forecast_bundles_to_simos_schedule(bundles)
    source_block = [{
        "entity": {"type": entity_type},
        "arrivals": arrivals_block,
        "entry_node": entry_node,
    }]
    return _YAML_HEADER + yaml.safe_dump({"sources": source_block}, sort_keys=False)
