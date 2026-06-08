"""Consumer adapters — in-process orchestration per CONTRACTS §3.

Per D1 library-first: these are Python function APIs, not HTTP clients.
v0.1.5 will materialize REST equivalents.

Adapters:
- simos_adapter — DemandForecastDistribution wrap + bulk-query interface
- planning_adapter — aggregated curves for PlanningOS SD (v0.1.5+)
- o2c_adapter — InventoryPolicy + PIR for Order2Cash_os (v0.1.5+)
"""

from demand_signal_os.consumers import simos_adapter, simos_arrivals_adapter

__all__ = ["simos_adapter", "simos_arrivals_adapter"]
