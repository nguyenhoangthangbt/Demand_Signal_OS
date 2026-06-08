"""DSO → SimOS arrival-rate schedule adapter.

Converts a sequence of ``ForecastBundle`` records (one per time bucket)
into a SimOS ``arrivals.schedule`` list — the YAML shape SimOS already
consumes via its ``ScheduleDistribution`` arrival path (see
``simulation_os/distributions/schedule.py``).

This is the arrival counterpart to the processing-time integration
shipped earlier in ``consumers/simos_adapter.py`` (DemandForecastDistribution).
Both adapters live on the DSO side — SimOS doesn't import anything from
DemandSignalOS. SimOS just consumes the YAML or the Distribution
instance via its registered extensibility points.

Per CONSTITUTION §10 wrap-vs-build decision (locked in v0.1 founding
draft, 2026-06-08), the arrival path uses SimOS's existing schedule
mechanism — no SimOS code change needed. This adapter just translates
the per-bucket mean forecast into a rate-per-hour schedule entry,
optionally with noise_std drawn from the forecast band width.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

import yaml

from demand_signal_os.ops_schemas import ForecastBundle


def _bucket_seconds(bundle: ForecastBundle) -> float:
    """Width of the bundle's bucket in seconds.

    Used to convert (units expected in bucket) → (rate per hour).
    """
    start = datetime.combine(bundle.bucket.start, datetime.min.time())
    end = datetime.combine(bundle.bucket.end, datetime.min.time())
    delta = end - start
    return float(delta.total_seconds()) or 86400.0  # default 1 day


def bundle_to_schedule_entry(
    bundle: ForecastBundle,
    *,
    t_seconds: float,
    noise_from_band: bool = True,
) -> dict[str, float]:
    """Convert a single ForecastBundle into a single SimOS schedule entry.

    Schedule entry shape (matches SimOS ScheduleEntry pydantic model):
        {time: <float seconds>, rate_per_hour: <float>, noise_std?: <float>}

    The ``rate_per_hour`` is derived from ``bundle.mean`` (units expected
    in the bucket) divided by the bucket width in hours. When
    ``noise_from_band=True``, ``noise_std`` is set to the q75-q25
    interquartile range divided by 1.349 (Gaussian-equivalent), so
    SimOS's ScheduleDistribution wobbles the rate around the forecast
    mean.
    """
    bucket_hours = _bucket_seconds(bundle) / 3600.0
    if bucket_hours <= 0:
        raise ValueError(f"bundle bucket has non-positive duration: {bucket_hours}h")
    rate_per_hour = float(bundle.mean) / bucket_hours

    entry: dict[str, float] = {
        "time": float(t_seconds),
        "rate_per_hour": rate_per_hour,
    }
    if noise_from_band:
        # IQR / 1.349 = Gaussian-equivalent sigma per textbook convention
        iqr = bundle.quantiles.q75 - bundle.quantiles.q25
        noise = max(iqr / 1.349, 0.0) / bucket_hours
        entry["noise_std"] = float(noise)
    return entry


def forecast_bundles_to_simos_schedule(
    bundles: Iterable[ForecastBundle],
    *,
    noise_from_band: bool = True,
    cycle_duration_seconds: float | None = None,
) -> dict[str, object]:
    """Convert a sequence of ForecastBundles into a SimOS arrivals block.

    Args:
        bundles: ForecastBundle records, one per consecutive time bucket
            (must share sku_id + location_id; an empty sequence raises
            ValueError).
        noise_from_band: Embed the bundle's IQR as noise_std on each
            schedule entry. Defaults to True so the SimOS arrivals
            stochasticity tracks the forecast uncertainty band.
        cycle_duration_seconds: When set, the SimOS arrivals block is
            marked as cyclic (the schedule restarts after this many
            seconds). When None (default), the schedule is treated as
            single-pass.

    Returns:
        A dict matching SimOS's arrivals block:
            {
                "distribution": "schedule",
                "schedule": [{"time": ..., "rate_per_hour": ..., ...}, ...],
                "cycle_duration": <float seconds, optional>,
            }
        Ready to be merged into a SimOS template config's
        ``arrivals`` field. The caller can then dump it via yaml.safe_dump
        or write_template.

    Raises:
        ValueError: empty bundles sequence, mixed sku/location, or
            non-monotone bucket starts.
    """
    bundle_list: Sequence[ForecastBundle] = list(bundles)
    if not bundle_list:
        raise ValueError("bundles is empty")

    # Validate identity (all bundles must be from the same SKU/location)
    head = bundle_list[0]
    for b in bundle_list[1:]:
        if b.sku_id != head.sku_id:
            raise ValueError(
                f"sku_id mismatch in bundles: {head.sku_id} vs {b.sku_id}"
            )
        if b.location_id != head.location_id:
            raise ValueError(
                f"location_id mismatch in bundles: {head.location_id} vs {b.location_id}"
            )

    # Validate monotone bucket starts (no overlap or duplicates)
    for i in range(1, len(bundle_list)):
        if bundle_list[i].bucket.start <= bundle_list[i - 1].bucket.start:
            raise ValueError(
                f"non-monotone bucket starts at index {i}: "
                f"{bundle_list[i - 1].bucket.start} -> {bundle_list[i].bucket.start}"
            )

    # Build schedule entries relative to t=0 at the first bucket's start
    base = datetime.combine(bundle_list[0].bucket.start, datetime.min.time())
    schedule: list[dict[str, float]] = []
    for b in bundle_list:
        start = datetime.combine(b.bucket.start, datetime.min.time())
        t = (start - base).total_seconds()
        schedule.append(bundle_to_schedule_entry(
            b, t_seconds=float(t), noise_from_band=noise_from_band
        ))

    out: dict[str, object] = {
        "distribution": "schedule",
        "schedule": schedule,
    }
    if cycle_duration_seconds is not None:
        out["cycle_duration"] = float(cycle_duration_seconds)
    return out


def write_simos_arrivals_yaml(
    bundles: Iterable[ForecastBundle],
    path: str | Path,
    *,
    noise_from_band: bool = True,
    cycle_duration_seconds: float | None = None,
    entity_type: str = "order",
    entry_node: str = "order_intake",
) -> None:
    """Convenience wrapper — converts bundles to SimOS arrivals block AND
    wraps in a complete source config block + writes to YAML.

    Produces a YAML fragment matching SimOS's multi-source ``sources``
    list shape:

        - entity:
            type: order
          arrivals:
            distribution: schedule
            schedule: [...]
          entry_node: order_intake

    Callers can ``yaml.safe_load`` this fragment, splice it into a
    template's ``sources`` list, and pass the result to
    ``simulation_os.config.loader.load_config()``.
    """
    arrivals_block = forecast_bundles_to_simos_schedule(
        bundles,
        noise_from_band=noise_from_band,
        cycle_duration_seconds=cycle_duration_seconds,
    )
    source_block = [{
        "entity": {"type": entity_type},
        "arrivals": arrivals_block,
        "entry_node": entry_node,
    }]
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"sources": source_block}, fh, sort_keys=False)
