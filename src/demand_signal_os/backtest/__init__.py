"""Backtest harness — M5-aligned walk-forward per BACKTESTING.md.

v0.1 deliverables (custom — NOT in Nixtla):
- Walk-forward rolling-origin evaluator (min 4 windows operational/tactical)
- Mandatory benchmarks: naive seasonal, SES, moving average
- Primary metrics: CRPS, sMAPE, WRMSSE, pinball q50/q90
- Secondary metric: WIS (~50 lines, custom)
"""

from demand_signal_os.backtest.metrics import crps, pinball_loss, smape, wis

__all__ = ["crps", "pinball_loss", "smape", "wis"]
