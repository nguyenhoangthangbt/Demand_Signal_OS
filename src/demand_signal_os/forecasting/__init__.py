"""Forecasting module — Nixtla wrap per CONSTITUTION §10.

Wraps statsforecast (ETS, CrostonOptimized, TSB, CrostonSBA) +
HierarchicalForecast (BottomUp). Custom code in this module is the
ForecastMethod protocol and the v0.1 method dispatch.

PER CONTRACTS §4 + §9: NO imports from inventory_policy/. Forecasting
produces ForecastBundle; inventory_policy consumes via that interface.
"""

from demand_signal_os.forecasting.protocol import ForecastMethod, ForecastRequest

__all__ = ["ForecastMethod", "ForecastRequest"]
