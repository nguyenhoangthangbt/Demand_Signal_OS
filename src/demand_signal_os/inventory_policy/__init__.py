"""Inventory policy math — the F2S-minimal core.

PER F2S_BOUNDARY.md + CONTRACTS §4 + §9: every capability here MUST be
textbook-citable, forecast-coupled, and configurable-not-customizable.
No imports from forecasting/<method>/ — only via ForecastBundle.

v0.1 policies (per CONSTITUTION §6):
- newsvendor — single-period perishable
- qr — (Q,R) continuous review
- ss — (s,S) periodic review (per-echelon for multi-echelon, R-7)
- base_stock — single-echelon lost-sales / backorder
- safety_stock — dual mode CSL + fill-rate (U3)
- pir — Planned Independent Requirements generation
"""

from demand_signal_os.inventory_policy import (
    base_stock,
    newsvendor,
    pir,
    qr,
    safety_stock,
    ss,
)

__all__ = ["base_stock", "newsvendor", "pir", "qr", "safety_stock", "ss"]
