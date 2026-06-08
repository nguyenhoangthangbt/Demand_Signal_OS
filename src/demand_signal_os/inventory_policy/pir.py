"""PIR (Planned Independent Requirement) generation.

Reference: NEO F2S.PI.S082 Demand Management — Display PIRs (NEO subprocess);
Hyndman & Athanasopoulos (2021).

PIRs are deterministic ERP-style artifacts derived from forecasts.
Per S7: NOT for SimOS (samples from ForecastBundle.distribution).
Consumers: PlanningOS (strategic flows) + Order2Cash_os (operational triggers)
+ future 0NEO/F2S_os/ MRP.

Per D5: PIR.quantiles is optional (default None) — ERP consumers expect
deterministic quantity_planned only.
"""

from __future__ import annotations

from demand_signal_os.ops_schemas import PIR, ForecastBundle


def pir_from_forecast(bundle: ForecastBundle, *, carry_quantiles: bool = False) -> PIR:
    """Generate a PIR from a ForecastBundle.

    Quantity = forecast median (q50). When carry_quantiles=True, the
    PIR carries the full quantile band for non-ERP consumers that can
    use it (e.g., PlanningOS scenario branching).
    """
    return PIR(
        sku_id=bundle.sku_id,
        location_id=bundle.location_id,
        bucket=bundle.bucket,
        quantity_planned=bundle.quantiles.q50,
        quantiles=bundle.quantiles if carry_quantiles else None,
        forecast_provenance=bundle.provenance,
    )
