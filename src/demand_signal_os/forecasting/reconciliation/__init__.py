"""Hierarchical reconciliation — Nixtla HierarchicalForecast wrapper.

v0.1 default: BottomUp (Hyndman & Athanasopoulos 2021 ch. 11.2).
v0.2 stretch: MinT with Schäfer-Strimmer shrinkage (Wickramasuriya et al. 2019).

Per CONTRACTS §5.4: reconciliation is pre-computed in a materialized pass,
NOT enforced at request time. Caller materializes for the full cube once
per forecast run.
"""

from demand_signal_os.forecasting.reconciliation.bottom_up import reconcile_bottom_up

__all__ = ["reconcile_bottom_up"]
