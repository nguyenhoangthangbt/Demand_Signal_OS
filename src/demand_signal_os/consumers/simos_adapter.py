"""SimOS adapter — DemandForecastDistribution wrap + bulk-query (R-4).

Per CONTRACTS §3.1: under D1 library-first, the bulk-pull "endpoint"
becomes a library function. When v0.1.5 lands the standalone API,
this same function signature becomes a REST endpoint.

REQUIRES SimOS-side prerequisite (per simos R2 finding): SimOS
config/loader.py adds `distribution_override` to ArrivalConfig +
build_simulation(). See CONSTITUTION §11 Phase 2.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from demand_signal_os.ops_schemas import ForecastBundle


class DemandForecastDistribution:
    """SimOS-samplable distribution wrapping a ForecastBundle's quantiles.

    Implements SimOS's Distribution protocol — `sample()` returns a draw
    via linear-interpolation inverse-CDF over the 7 canonical quantiles.

    Registered into SimOS's distributions/registry.py via:
        from simulation_os.distributions import register
        register("demand_forecast", DemandForecastDistribution)
    """

    def __init__(self, bundle: ForecastBundle, *, seed: int | None = None):
        self._q = bundle.quantiles
        self._rng = np.random.default_rng(seed)
        self._levels = np.array([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
        self._values = np.array(
            [
                self._q.q05, self._q.q10, self._q.q25, self._q.q50,
                self._q.q75, self._q.q90, self._q.q95,
            ]
        )

    def sample(self) -> float:
        """One draw via linear-interpolation inverse-CDF."""
        u = float(self._rng.uniform(self._levels[0], self._levels[-1]))
        return float(np.interp(u, self._levels, self._values))


# Bulk-query interface — replaces v0.1.5 REST bulk endpoint per R-4
ForecastResolver = Callable[[str, str, str], ForecastBundle | None]


def forecast_bulk(
    sku_ids: list[str],
    location_ids: list[str],
    horizon: str,
    resolver: ForecastResolver,
) -> dict[tuple[str, str], ForecastBundle]:
    """Resolve forecasts for a cube of (sku, location) at a given horizon.

    `resolver` is injected so the adapter doesn't depend on a specific
    storage backend — the v0.1 forecasting engine produces it; the
    v0.1.5 API replaces it with a DB-backed implementation.
    """
    out: dict[tuple[str, str], ForecastBundle] = {}
    for sku in sku_ids:
        for loc in location_ids:
            bundle = resolver(sku, loc, horizon)
            if bundle is not None:
                out[(sku, loc)] = bundle
    return out
