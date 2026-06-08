# BACKTESTING — DemandSignalOS evaluation protocol

> M5-aligned walk-forward evaluation. Every forecasting method must beat the mandatory baselines on the canonical metrics; methods that don't are documented but excluded from production use.

**Status:** v0.1 founding draft (2026-06-08) on `feat/founding-design`. Created per Round 1 litreview finding U5.

---

## 1. Why this document exists

The v0 founding draft specified ETS / Croston / TSB / SBA / GBM as v0.1 methods but did not specify how to evaluate them. Without a protocol, every method "looks correct" on cherry-picked data, and the engine has no defensible accuracy claim. This document fixes that.

The protocol is **M5-aligned** — it follows the structure of the M5 Accuracy competition (Makridakis, Spiliotis & Assimakopoulos 2022, *IJF* 38(4), 1346–1364) which evaluated 42,840 hierarchical retail time series with rolling-origin walk-forward and the WRMSSE primary metric. M5 is the modern benchmark; aligning with it makes DemandSignalOS results comparable to published research and to enterprise IBP vendor claims.

---

## 2. Walk-forward design

### 2.1 Rolling-origin evaluation

Walk-forward (also called "rolling origin" or "rolling window"):

```
Window 1:  [-------- train --------] [eval] . . . . . .
Window 2:  [---------- train ----------] [eval] . . . .
Window 3:  [------------ train ------------] [eval] . .
...
```

Each window:
- Trains on all data BEFORE the window-specific `data_cut_timestamp`
- Evaluates on the next H buckets (the forecast horizon)
- Strictly no lookahead — `ForecastProvenance.data_cut_timestamp` enforces the train/test split

### 2.2 Number of windows per horizon

| Horizon | Window count | Each window covers |
|---|---|---|
| **Operational** (30-day) | **min 4 windows**, non-overlapping | 30 buckets ahead |
| **Tactical** (6-month) | **min 4 windows**, non-overlapping | 6 buckets ahead |
| **Strategic** (18-month) | **min 2 windows** (data permitting) | 18 buckets ahead |

Reasoning: 4 windows is the minimum to get a defensible mean + variance of accuracy. M5 used 28-day windows over a 1.5-year span. Where history permits, expand to 6–8 windows.

### 2.3 Data cut handling

- `data_cut_timestamp` in `ForecastProvenance` is the boundary — strictly no information after this timestamp influences the forecast.
- Test-set censoring discipline: if the test bucket period had a stockout (per `CensoringFlag`), it is **excluded from the error metric** for that bucket. Including censored zeros as actuals would penalize correct forecasts.
- Seasonality boundary: windows must align to seasonal cycle boundaries (weekly windows align to weeks, monthly to months) to avoid artificially favoring methods that exploit boundary effects.

---

## 3. Mandatory benchmarks

Every method MUST be evaluated alongside these benchmarks on the same windows + metrics. A method that fails to beat all three benchmarks on a SKU is excluded from production use for that SKU (the engine falls back to the best-performing benchmark).

| Benchmark | Implementation | When it's the right floor |
|---|---|---|
| **Naïve seasonal** | `forecast[h] = actual[h - season_length]` | Any seasonal series (weekly, monthly, yearly) |
| **SES** (Simple Exponential Smoothing) | `forecast[h] = α · last_actual + (1 − α) · last_forecast`, α via MLE | Non-seasonal series with stable level |
| **Moving Average** | `forecast[h] = mean(last N actuals)`, N = 4 default | Stable-mean series, low variance |

Rationale: every forecasting paper since Makridakis has shown that simple benchmarks beat complex methods on a significant fraction of series. Mandatory benchmarks force the engine to be honest about which SKUs need complex methods and which don't.

---

## 4. Primary metrics

### 4.1 CRPS (Continuous Ranked Probability Score)

The standard strictly-proper scoring rule for probabilistic forecasts. The primary metric for research-grade evaluation.

Reference: Gneiting, T. & Raftery, A.E. (2007), "Strictly proper scoring rules, prediction, and estimation," *Journal of the American Statistical Association* 102(477), 359–378.

Lower is better. Computed per (SKU, location, bucket) and aggregated.

### 4.2 sMAPE (Symmetric Mean Absolute Percentage Error)

Standard point-forecast metric:

```
sMAPE = mean(2 · |actual - forecast| / (|actual| + |forecast|))
```

Lower is better. Undefined when both actual and forecast are zero (skip).

### 4.3 WRMSSE (Weighted Root Mean Squared Scaled Error)

The M5 primary metric. Scale-free, so series with different magnitudes are comparable. Weighted by dollar value or unit volume for prioritization across SKUs.

```
RMSSE = sqrt(mean((forecast - actual)² / scale²))
WRMSSE = sum(weight_i · RMSSE_i)
scale = mean(diff(historical_actuals)²)  # MASE-style scaling
```

Reference: Makridakis, Spiliotis & Assimakopoulos (2022), *IJF* 38(4), 1346–1364.

Used for cross-SKU comparison and aggregate engine accuracy reporting.

### 4.4 Pinball loss (quantile loss)

Standard for quantile-based forecasts:

```
pinball_α(y, q) = (y - q) · α   if y >= q
                = (q - y) · (1 - α)  if y < q
```

Computed at q50 (median) and q90 (90th percentile) per `ForecastAccuracy` schema. Q50 measures central tendency accuracy; Q90 measures upper-tail accuracy critical for stockout-risk quantification.

### 4.5 MAPE (with caveat)

Reported when defined (excluded for intermittent series with zero actuals — `mape: float | None` in `ForecastAccuracy`).

---

## 5. Secondary metric — WIS (Weighted Interval Score)

Per Round 2 litreview refinement R-3: WIS is implemented as a custom backtest metric in this v0.1 harness (~50 lines), but NOT included in the core `ForecastAccuracy` schema (deferred to v0.2 schema inclusion).

WIS is the standard proper score for interval-based forecasts. More communicable to non-specialist stakeholders than CRPS because it decomposes into sharpness + calibration components.

```
WIS = (1/(K+0.5)) · (0.5 · |y - median| 
       + Σ_k (α_k/2) · (upper_k - lower_k 
                        + (2/α_k)·(lower_k - y)·I(y < lower_k) 
                        + (2/α_k)·(y - upper_k)·I(y > upper_k)))
```

Reference: Bracher, J., Ray, E.L., Gneiting, T. & Reich, N.G. (2021), "Evaluating epidemic forecasts in an interval format," *PLOS Computational Biology* 17(2), e1008618.

Implemented in `backtest/metrics.py` as `def wis(quantiles: Quantiles, actual: float, alphas: list[float]) -> float`. Reported in backtest summary tables, not in production `ForecastAccuracy` records.

---

## 6. Reporting

### 6.1 Per-method, per-SKU summary

Each backtest run produces a table:

| sku_id | location_id | method | window | crps | smape | wrmsse | pinball_q50 | pinball_q90 | wis |
|---|---|---|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

### 6.2 Aggregate engine accuracy

Aggregate by:
- Method (ETS vs CrostonOpt vs TSB vs SBA vs GBM vs each benchmark)
- ABC class (A vs B vs C SKUs)
- Demand pattern (smooth / intermittent / erratic / lumpy per Syntetos-Boylan classification, v0.1.5+)
- Forecast horizon (operational / tactical / strategic)

Report: mean + std + 95% CI per cell.

### 6.3 Method selection criterion

For each (SKU, location), the production engine uses the method with the best **CRPS** averaged across windows, subject to beating ALL THREE mandatory benchmarks (Naïve seasonal, SES, Moving Average). If no candidate beats all benchmarks, the engine falls back to the best-performing benchmark for that SKU and flags `fallback_applied = FallbackStrategy(strategy_type="cold_start" if insufficient history else None, fallback="empirical_only")` per CONTRACTS §8.

---

## 7. Reproducibility

### 7.1 Seeded RNG

Every backtest run carries `seed: int` in `ForecastProvenance`. Re-running with the same (data_cut_timestamp, seed, commit_sha, feature_set_hash) MUST produce byte-identical results.

### 7.2 Frozen data cuts

Backtest data cuts are documented as `data_cut_timestamp` per window. Once a backtest is published, the data cut is frozen — re-evaluation uses the same historical snapshot.

### 7.3 Versioning

Backtest results are versioned alongside the engine commit_sha. A backtest result at engine v0.1 cannot be compared directly to a backtest at v0.2 unless re-run on the same data cuts.

---

## 8. References

- Makridakis, S., Spiliotis, E. & Assimakopoulos, V. (2022). "M5 accuracy competition: Results, findings, and conclusions." *International Journal of Forecasting* 38(4), 1346–1364.
- Gneiting, T. & Raftery, A.E. (2007). "Strictly proper scoring rules, prediction, and estimation." *Journal of the American Statistical Association* 102(477), 359–378.
- Bracher, J., Ray, E.L., Gneiting, T. & Reich, N.G. (2021). "Evaluating epidemic forecasts in an interval format." *PLOS Computational Biology* 17(2), e1008618.
- Hyndman, R.J. & Athanasopoulos, G. (2021). *Forecasting: Principles and Practice* (3rd ed.). OTexts: Melbourne. (Ch. 5.10 "Evaluating point forecast accuracy"; ch. 5.11 "Distributional accuracy.")
- Olivares, K.G., Garza, F. & Canseco, M.M. (2023). "Hierarchical forecasting with Nixtla: A Python framework for interpretable and scalable forecasting." *Journal of Open Source Software* 8(84), 5233.
