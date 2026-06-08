"""Lead-time distribution estimation from O2C historical observations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LeadTimeDistribution:
    mean_periods: float
    std_periods: float
    samples: np.ndarray  # for empirical sampling

    @classmethod
    def from_observations(cls, observations: list[float]) -> "LeadTimeDistribution":
        if not observations:
            raise ValueError("at least one observation required")
        arr = np.asarray(observations, dtype=float)
        return cls(
            mean_periods=float(np.mean(arr)),
            std_periods=float(np.std(arr)),
            samples=arr,
        )
