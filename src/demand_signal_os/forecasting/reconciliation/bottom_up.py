"""Bottom-up reconciliation per CONTRACTS §5.3.

Sum bottom-level forecasts per quantile to produce aggregate-level
forecasts. Trivial implementation — robustness comes from doing it
consistently across all 7 quantiles.
"""

from __future__ import annotations

from collections.abc import Iterable

from demand_signal_os.ops_schemas import ForecastBundle, Quantiles


def _sum_quantiles(qs: list[Quantiles]) -> Quantiles:
    return Quantiles(
        q05=sum(q.q05 for q in qs),
        q10=sum(q.q10 for q in qs),
        q25=sum(q.q25 for q in qs),
        q50=sum(q.q50 for q in qs),
        q75=sum(q.q75 for q in qs),
        q90=sum(q.q90 for q in qs),
        q95=sum(q.q95 for q in qs),
    )


def reconcile_bottom_up(
    bottom_bundles: Iterable[ForecastBundle],
    aggregate_provenance,
    aggregate_sku_id: str,
    aggregate_location_id: str,
) -> ForecastBundle:
    """Bottom-up reconciliation: sum quantiles + mean across bottom bundles.

    All bottom bundles MUST share the same bucket + horizon_label.
    """
    bottom = list(bottom_bundles)
    if not bottom:
        raise ValueError("at least one bottom bundle required")

    bucket = bottom[0].bucket
    horizon = bottom[0].horizon_label
    if any(b.bucket != bucket for b in bottom):
        raise ValueError("all bottom bundles must share the same bucket")
    if any(b.horizon_label != horizon for b in bottom):
        raise ValueError("all bottom bundles must share horizon_label")

    return ForecastBundle(
        sku_id=aggregate_sku_id,
        location_id=aggregate_location_id,
        bucket=bucket,
        horizon_label=horizon,
        quantiles=_sum_quantiles([b.quantiles for b in bottom]),
        mean=sum(b.mean for b in bottom),
        method="bottom_up",
        provenance=aggregate_provenance,
    )
