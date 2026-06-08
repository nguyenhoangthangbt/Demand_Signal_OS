"""DEPRECATED-AS-CANONICAL — types live in ``ops_schemas`` (top-level
shared package at ``platforms_os/packages/ops_schemas/``).

This shim re-exports the promoted types so every pre-existing
``from demand_signal_os.ops_schemas import ...`` site continues to work
byte-for-byte. New consumers should import from ``ops_schemas`` directly
to avoid the transitive DSO dependency cost.

Promoted 2026-06-08 per CONSTITUTION §8 policy. Trigger met by the
PlanningOS production wire-up (Phase D) + the SimOS arrival adapter
(Phase B) — both need typed access to the boundary language without
pulling in scipy / lightgbm / statsforecast / pandas.

Install order in dev:
    pip install -e platforms_os/packages/ops_schemas
    pip install -e platforms_os/Demand_Signal_OS
"""

from ops_schemas import (  # re-export
    PIR,
    SKU,
    ArchetypeTag,
    BaseStockParameters,
    CensoringFlag,
    DemandActual,
    DemandSignal,
    ForecastAccuracy,
    ForecastBundle,
    ForecastFallbackStrategy,
    ForecastProvenance,
    InventoryPolicy,
    Location,
    NewsvendorParameters,
    PolicyParameters,
    ProbabilisticDistribution,
    QRParameters,
    Quantiles,
    ReorderTrigger,
    SSParameters,
    TimeBucket,
)

__all__ = [
    "PIR",
    "SKU",
    "ArchetypeTag",
    "BaseStockParameters",
    "CensoringFlag",
    "DemandActual",
    "DemandSignal",
    "ForecastAccuracy",
    "ForecastBundle",
    "ForecastFallbackStrategy",
    "ForecastProvenance",
    "InventoryPolicy",
    "Location",
    "NewsvendorParameters",
    "PolicyParameters",
    "ProbabilisticDistribution",
    "QRParameters",
    "Quantiles",
    "ReorderTrigger",
    "SSParameters",
    "TimeBucket",
]
