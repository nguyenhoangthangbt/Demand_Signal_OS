"""Forecast -> SimOS arrivals YAML exporter (the DSO→SimOS contract).

The machine-handoff peer of the .xlsx export. Humans audit the workbook; SimOS
consumes THIS: a ``sources``/``arrivals.schedule`` YAML block that SimOS's
config loader ingests directly (``simulation_os.config.loader``). Reuses the
tested ``consumers.simos_arrivals_adapter`` so the rate/noise math + robustness
guards are byte-identical to the in-process integration — this is the same
contract, just serialized for download instead of wired in memory.

The per-horizon forecast (a ``forecast_path`` of ``Quantiles``) becomes one
schedule entry per step (a real widening band → widening ``noise_std``).

Hand-off basis (2026-10-13, customer journey C-01). A forecast value is "demand
per period"; SimOS needs "entities per hour". The conversion depends on facts
only the customer knows: how long one period is (day, week, month), whether the
numbers count orders or units (and how many units make one order), and how many
hours a day and days a week the site operates. ``SimosHandoff`` carries those
facts; every export states them in its header so the rate is never a silent
guess. Without an explicit basis the old reading applies (each value is demand
per ``bucket_period`` over a 24 h, 7 day calendar), which gives the same
schedule numbers as the pre-2026-10-13 export.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

# Average days in a calendar month (365.25 / 12). Used only to turn "per
# month" into operating hours; a fixed constant keeps the export deterministic.
DAYS_PER_MONTH = 365.25 / 12.0

_PERIOD_WORD = {"day": "day", "week": "week", "month": "month"}


def _fmt(x: float) -> str:
    """Short, stable number text for headers (no trailing zeros)."""
    return f"{float(x):.4f}".rstrip("0").rstrip(".")


class SimosHandoff(BaseModel):
    """What one forecast number means, stated by the customer before export."""

    data_frequency: Literal["day", "week", "month"] = Field(
        description="how long one value in the series covers",
    )
    demand_unit: Literal["orders", "units"] = Field(
        default="orders", description="whether each value counts orders or units",
    )
    units_per_order: float = Field(
        default=1.0, gt=0, le=1_000_000,
        description="units in one order; used only when demand_unit is units",
    )
    operating_hours_per_day: float = Field(default=24.0, gt=0, le=24)
    operating_days_per_week: float = Field(default=7.0, gt=0, le=7)

    def hours_per_period(self) -> float:
        """Operating hours one forecast value is spread over."""
        h = float(self.operating_hours_per_day)
        if self.data_frequency == "day":
            return h
        d = float(self.operating_days_per_week)
        if self.data_frequency == "week":
            return h * d
        return h * d * DAYS_PER_MONTH / 7.0

    def units_per_entity(self) -> float:
        return float(self.units_per_order) if self.demand_unit == "units" else 1.0

    def describe(self) -> str:
        """One plain sentence stating the conversion (for headers and the UI)."""
        per = _PERIOD_WORD[self.data_frequency]
        what = "units" if self.demand_unit == "units" else "orders"
        text = (
            f"Each forecast value is {what} per {per}, spread over "
            f"{_fmt(round(self.hours_per_period(), 1))} operating hours "
            f"({_fmt(self.operating_hours_per_day)} h a day, "
            f"{_fmt(self.operating_days_per_week)} days a week)"
        )
        if self.demand_unit == "units":
            n = _fmt(self.units_per_order)
            text += f", with {n} {'unit' if n == '1' else 'units'} per order"
        return text + ". SimOS receives orders per operating hour."


def default_handoff(bucket_period: str) -> SimosHandoff:
    """The pre-2026-10-13 reading: each value is orders per ``bucket_period``
    on a 24 h, 7 day calendar (same schedule numbers as the old export)."""
    freq = bucket_period if bucket_period in _PERIOD_WORD else "day"
    return SimosHandoff(data_frequency=freq)  # type: ignore[arg-type]


def _header(handoff: SimosHandoff) -> str:
    return (
        _YAML_HEADER
        + f"# Conversion: {handoff.describe()}\n"
        + "# The schedule clock counts operating hours: entry i starts at\n"
        + f"# i x {_fmt(handoff.hours_per_period())} h. entry_node is a placeholder; SimOS\n"
        + "# Builder 'Import YAML' keeps your model and replaces only its arrivals.\n"
    )

_YAML_HEADER = (
    "# SimOS arrivals: generated from a DemandSignalOS forecast.\n"
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


def forecast_to_simos_schedule(
    winner_bundle: Any,
    path: list[Any],
    *,
    bucket_period: str = "day",
    start_date: date | None = None,
    handoff: SimosHandoff | None = None,
) -> dict[str, Any]:
    """The SimOS ``arrivals`` block for a forecast under a stated hand-off
    basis (``default_handoff(bucket_period)`` when none is given)."""
    from demand_signal_os.consumers.simos_arrivals_adapter import (
        forecast_bundles_to_simos_schedule,
    )

    basis = handoff or default_handoff(bucket_period)
    base = start_date or date(2026, 1, 1)
    bundles = (
        _horizon_bundles(winner_bundle, path, bucket_period=bucket_period, start_date=base)
        if path
        else [winner_bundle]
    )
    return forecast_bundles_to_simos_schedule(
        bundles,
        hours_per_bucket=basis.hours_per_period(),
        units_per_entity=basis.units_per_entity(),
    )


def simos_handoff_preview(
    winner_bundle: Any,
    path: list[Any],
    *,
    bucket_period: str = "day",
    start_date: date | None = None,
    handoff: SimosHandoff | None = None,
) -> dict[str, Any]:
    """What the SimOS export will contain, for the customer to confirm first:
    per period, the forecast median and the converted orders per hour."""
    basis = handoff or default_handoff(bucket_period)
    block = forecast_to_simos_schedule(
        winner_bundle, path, bucket_period=bucket_period,
        start_date=start_date, handoff=basis,
    )
    medians = [float(q.q50) for q in path] if path else [float(winner_bundle.mean)]
    steps = []
    for i, (entry, med) in enumerate(zip(block["schedule"], medians)):
        steps.append({
            "period": i + 1,
            "forecast_median": med,
            "starts_at_hour": float(entry["time"]) / 3600.0,
            "rate_per_hour": float(entry["rate_per_hour"]),
            "noise_std": float(entry.get("noise_std", 0.0)),
        })
    return {
        "basis": basis.model_dump(mode="json"),
        "hours_per_period": basis.hours_per_period(),
        "units_per_order": basis.units_per_entity(),
        "explanation": basis.describe(),
        "steps": steps,
    }


def forecast_to_simos_arrivals_xlsx(
    winner_bundle: Any,
    path: list[Any],
    *,
    bucket_period: str = "day",
    start_date: date | None = None,
    handoff: SimosHandoff | None = None,
) -> bytes:
    """The DSO->SimOS arrivals contract as a list-valued xlsx (the same shape
    SimOS's excel-builder accepts). Declares ``arrivals_distribution=schedule``
    and fills the Arrival Schedule sheet with one row per horizon step
    ``(time, rate_per_hour, noise_std)`` from the forecast's widening band."""
    from excel_io import arrivals_schedule_spec, generate_xlsx

    block = forecast_to_simos_schedule(
        winner_bundle, path, bucket_period=bucket_period,
        start_date=start_date, handoff=handoff,
    )
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
    handoff: SimosHandoff | None = None,
) -> str:
    """Serialize a forecast into a SimOS arrivals YAML string.

    ``path`` is a ``forecast_path`` (list of ``Quantiles``, one per horizon
    step). Falls back to the single terminal ``winner_bundle`` when the path is
    empty. Returns the YAML text (with an explanatory header) — the caller
    streams it as a download.
    """
    basis = handoff or default_handoff(bucket_period)
    arrivals_block = forecast_to_simos_schedule(
        winner_bundle, path, bucket_period=bucket_period,
        start_date=start_date, handoff=basis,
    )
    source_block = [{
        "entity": {"type": entity_type},
        "arrivals": arrivals_block,
        "entry_node": entry_node,
    }]
    return _header(basis) + yaml.safe_dump({"sources": source_block}, sort_keys=False)
