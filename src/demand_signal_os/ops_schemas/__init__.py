"""ops_schemas — the boundary language of the Planning2Cash loop.

LOCATION POLICY (per CONSTITUTION §8 + CONTRACTS §1):

- **v0.1 (now):** nested here under `demand_signal_os.ops_schemas`.
  No external consumer imports these types yet — YAGNI rules.

- **Promotion trigger:** the first SimOS-side or PlanningOS-side line
  that does `from demand_signal_os.ops_schemas import ...`. At that
  point the transitive-dependency cost (scipy / lightgbm / pandas) lands
  on the consumer's environment for no business-logic reason — that's
  the signal to extract.

- **Promotion target:** `platforms_os/packages/ops_schemas/` (NOT
  `platforms_os/ops_schemas/` — shared infrastructure lives under
  `packages/`, distinct from platforms at the top level).

The promotion itself is mechanical: move the 6 modules + rename imports
across all consumers in one PR. No API change.
"""

from demand_signal_os.ops_schemas.accuracy import ForecastAccuracy
from demand_signal_os.ops_schemas.demand import (
    CensoringFlag,
    DemandActual,
    DemandSignal,
)
from demand_signal_os.ops_schemas.fallback import ForecastFallbackStrategy
from demand_signal_os.ops_schemas.forecast import (
    ForecastBundle,
    ForecastProvenance,
    ProbabilisticDistribution,
    Quantiles,
)
from demand_signal_os.ops_schemas.hierarchy import (
    SKU,
    ArchetypeTag,
    Location,
    TimeBucket,
)
from demand_signal_os.ops_schemas.policy import (
    PIR,
    BaseStockParameters,
    InventoryPolicy,
    NewsvendorParameters,
    PolicyParameters,
    QRParameters,
    ReorderTrigger,
    SSParameters,
)

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
