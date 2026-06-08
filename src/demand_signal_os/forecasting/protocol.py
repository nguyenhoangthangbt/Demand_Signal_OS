"""ForecastMethod protocol — the adapter boundary per CONSTITUTION §10.

Every forecasting backend (Nixtla wrappers, custom GBM, future deep-learning)
implements this protocol. The wrap boundary is the ForecastBundle contract;
swapping backends is a config change, not a code change.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol

import numpy as np
from pydantic import BaseModel

from demand_signal_os.ops_schemas import ForecastBundle, TimeBucket


class ForecastRequest(BaseModel):
    """Input bundle for ForecastMethod.fit_predict.

    Per CONSTITUTION §8 library-first design rule #2: forecast path is a
    pure function of (data, config, seed). All I/O happens before this point.
    """

    sku_id: str
    location_id: str
    history: list[float]  # historical actuals in time order
    history_buckets: list[TimeBucket]
    horizon_buckets: list[TimeBucket]  # buckets to forecast
    horizon_label: Literal["operational", "tactical", "strategic"]
    seed: int
    data_cut_timestamp: datetime
    method_config: dict = {}


class ForecastMethod(Protocol):
    """The adapter interface — wraps Nixtla, custom, or future backends."""

    method_id: str  # e.g. "ets", "croston_opt", "tsb", "sba", "gbm"

    def fit_predict(self, request: ForecastRequest) -> ForecastBundle:
        """Produce a ForecastBundle. Pure function of request inputs."""
        ...


def quantiles_from_samples(samples: np.ndarray) -> dict[str, float]:
    """Compute the 7 canonical quantiles from a sample array.

    Pure utility — used by every wrapper to emit Quantiles consistently.
    """
    q_levels = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
    qs = np.quantile(samples, q_levels)
    return {
        "q05": float(qs[0]),
        "q10": float(qs[1]),
        "q25": float(qs[2]),
        "q50": float(qs[3]),
        "q75": float(qs[4]),
        "q90": float(qs[5]),
        "q95": float(qs[6]),
    }
