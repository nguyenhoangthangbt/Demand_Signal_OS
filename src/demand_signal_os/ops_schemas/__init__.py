"""ops_schemas — the boundary language of the Planning2Cash loop.

NOTE: per CONSTITUTION §8 + CONTRACTS §1, this package is intended to be
PROMOTED to a top-level shared package at `platforms_os/ops_schemas/`
once coordinated with the sibling session working in that repo. Until
then, it lives here and other platforms import as
`demand_signal_os.ops_schemas`. The promotion is mechanical (move +
update import paths) — no API change.
"""

from demand_signal_os.ops_schemas.demand import (
    CensoringFlag,
    DemandActual,
    DemandSignal,
)
from demand_signal_os.ops_schemas.forecast import (
    ForecastBundle,
    ForecastProvenance,
    ProbabilisticDistribution,
    Quantiles,
)
from demand_signal_os.ops_schemas.hierarchy import (
    ArchetypeTag,
    Location,
    SKU,
    TimeBucket,
)
from demand_signal_os.ops_schemas.policy import (
    BaseStockParameters,
    InventoryPolicy,
    NewsvendorParameters,
    PolicyParameters,
    PIR,
    QRParameters,
    ReorderTrigger,
    SSParameters,
)
from demand_signal_os.ops_schemas.accuracy import ForecastAccuracy
from demand_signal_os.ops_schemas.fallback import ForecastFallbackStrategy

__all__ = [
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
    "PIR",
    "PolicyParameters",
    "ProbabilisticDistribution",
    "QRParameters",
    "Quantiles",
    "ReorderTrigger",
    "SKU",
    "SSParameters",
    "TimeBucket",
]
