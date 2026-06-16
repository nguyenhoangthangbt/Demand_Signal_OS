# DemandSignalOS — CONSTITUTION

> Probabilistic demand signal engine for the Planning2Cash internal playground.
> Forecast honestly. Reconcile hierarchically. Hand probabilistic outputs to every downstream consumer without information loss.

**Status:** v0.1 founding draft (2026-06-08) on branch `feat/founding-design`. Revised from v0 after two rounds of MAO triangulation (architect / simos_consultant / litreview_simos_cli / brainstormer Round 1; architect / simos_consultant / litreview_simos_cli Round 2). All 16 Round-1 revisions + 7 Round-2 refinements applied.

**Repo:** `github.com/nguyenhoangthangbt/Demand_Signal_OS` — sibling to `simulation_os/`, `Planning_os/`, `AlgoTrade_os/`, `LitReview_os/`, `Analytic_os/`. Cloned under `platforms_os/Demand_Signal_OS/`.

**Port slot:** 8006 (reserved for v0.1.5 API extraction; v0.1 ships as library only — see §11).

---

## 1. Mission

DemandSignalOS is the **missing forecasting + inventory-policy leg** of the Planning2Cash loop. It converts historical, transactional, and external signals into **probabilistic demand forecasts** and **inventory-policy decisions** that downstream platforms (SimOS, PlanningOS, Order2Cash_os) can consume natively — without flattening uncertainty to point forecasts at any boundary.

It exists because:

1. SimOS (DES), PlanningOS (SD), and Order2Cash_os all treat demand as an **input** today. None of them generate the signal that drives the loop.
2. Hand-authored YAML and generic distributions are the current stopgap — sufficient for engineering tests, insufficient for honest dogfooding.
3. Market-leading IBP vendors (Blue Yonder, o9, Kinaxis, SAP IBP) win on forecast accuracy. Without a probabilistic forecasting engine, Planning2Cash structurally cannot be a "plan-from-signal" loop, only an "execute-given-inputs" loop.

## 2. Scope — what it IS

- **Probabilistic demand forecasting** across three horizons (operational / tactical / strategic) with native quantile outputs.
- **Hierarchical reconciliation** so SD-aggregate, DES-entity, and O2C-transactional views share a single consistent forecast.
- **Stockout-censored estimation** — explicit handling of when zeros are real zeros vs. censored stockout periods.
- **Inventory-policy math** — safety-stock, reorder-point, (Q,R), (s,S), base-stock, PIR (Planned Independent Requirement) generation. The generalizable mathematical core of F2S, scoped per `F2S_BOUNDARY.md`.
- **Backtesting harness** — walk-forward, M5-aligned, cost-aware evaluation (service-level vs. holding-cost vs. stockout-cost tradeoff curves). See `BACKTESTING.md`.
- **Configuration-time customer fit** — every customer-variable parameter (service levels, lead times, distributions, ABC class) lives in YAML config, never in code.

## 3. Scope — what it is NOT

- **NOT a planning engine.** PlanningOS owns strategic SD flows; DemandSignalOS feeds it, does not replace it.
- **NOT a discrete-event simulator.** SimOS owns DES; DemandSignalOS emits the demand distributions SimOS samples from.
- **NOT a transactional system.** Order2Cash_os owns order-intake and fulfillment; DemandSignalOS does not record orders.
- **NOT operational F2S** (ERP subprocesses: substitution, supersession, batch, quality, DC-to-DC rebalancing, inbound delivery, destructions, lifecycle). Those are explicitly OUT per `F2S_BOUNDARY.md` and reserved for a future `0NEO/F2S_os/` commercial sibling to Order2Cash_os.
- **NOT a price/market forecaster.** AlgoTrade OS owns market signals. DemandSignalOS may reuse AlgoTrade's data-pipeline infrastructure (transferable ~40%), but the modeling domain (intermittent demand, censoring, hierarchical reconciliation, promotional uplift) is supply-chain-specific.
- **NOT an ML/RL operating-decision optimizer.** ML/RL OS was retired 2026-03-17 because SimOS + optimization is sufficient for operations decisions. DemandSignalOS is time-series forecasting *as input* to the existing platforms, not RL over decisions.
- **NOT a generic universal engine.** v0.1 targets ONE archetype (discrete manufacturing distribution); adjacent archetypes (pharma, fashion, grocery, automotive) layer in v0.2+.

## 4. v0.1 archetype focus

**Target:** Discrete manufacturing distribution.

| Property | Choice for v0.1 |
|---|---|
| Demand shape | Lumpy + often intermittent, lead-time-dominated |
| SKU count | 100s–10,000s per location |
| Location structure | Multi-echelon (factory → DC → regional DC) |
| Forecast horizons | 30 days (operational) / 6 months (tactical) / 18 months (strategic) |
| Distinguishing math | Croston/TSB/SBA for intermittents, (s,S) for multi-echelon DC, hierarchical reconciliation |
| Rationale | Closest archetype to existing O2C lighthouse domain; cleanest test against SimOS DES + PlanningOS SD |

Adjacent archetypes documented as roadmap layers, not v0.1 surface:

- **Pharma / regulated** — shelf-life-constrained newsvendor, batch tracking (v0.3+)
- **Fashion / short-cycle** — analog-based NPI, fast/slow-mover splits (v0.3+)
- **Grocery / FMCG** — daily-reorder, promo uplift dominant (v0.4+)
- **Automotive / OEM** — MRP, BOM-coupled (v0.5+)

## 5. v0.1 forecasting methods

Five methods (three primary + two intermittent variants), all wrapped from Nixtla per §10. Chosen for orthogonal coverage and explainability.

| Method | Why | Nixtla class | Reference |
|---|---|---|---|
| **ETS** (Error-Trend-Seasonal state-space) | Seasonal, steady-volume series. Probabilistic via state-space innovations. | `AutoETS` | Hyndman et al. (2008), *Forecasting with Exponential Smoothing*; Hyndman & Athanasopoulos (2021), *Forecasting: Principles and Practice* (3rd ed.) |
| **CrostonOptimized** *(default Croston variant)* | Intermittent demand with MLE-optimized smoothing parameter (strictly better than fixed α=0.1) | `CrostonOptimized` | Croston (1972), *Operational Research Quarterly* 23(3) |
| **TSB** | Intermittent with obsolescence handling — decomposes inter-demand intervals from demand sizes; separate `alpha_d` (demand) + `alpha_p` (probability) smoothing | `TSB` | Teunter, Syntetos & Babai (2011), *EJOR* 214(3), 606–615 |
| **SBA** *(canonical intermittent benchmark)* | Croston with Syntetos-Boylan 0.95 debiasing factor — the standard benchmark for intermittent-demand studies since 2005 | `CrostonSBA` | Syntetos & Boylan (2005), *IJF* 21(2), 303–314 |
| **Gradient-boosting (LightGBM quantile)** | Explainable (SHAP), non-linear, multivariate. Quantile loss for probabilistic outputs. | `SklearnModel` wrapping LightGBM | Hyndman & Athanasopoulos (2021) ch. 12; LightGBM quantile regression |

**Mandatory benchmarks** (M5-aligned, every method must beat in backtest):

| Benchmark | Why mandatory |
|---|---|
| **Naïve seasonal** | The "must-beat" floor for any seasonal series |
| **SES** (Simple Exponential Smoothing) | Floor for non-seasonal series |
| **Moving Average** | Floor for stable-mean series |

See `BACKTESTING.md` for the full evaluation protocol.

**Hierarchical reconciliation:** Bottom-up is the **v0.1 default** — robust, no covariance estimation, guaranteed coherence, O(N·Q) compute (Hyndman & Athanasopoulos 2021, ch. 11.2). MinT with Schäfer-Strimmer shrinkage (`mint_shrink`, Wickramasuriya-Athanasopoulos-Hyndman 2019; Schäfer & Strimmer 2005) is a **v0.2 stretch** — at 10k SKU × 10 location = 100k bottom series scale, MinT requires a 100k×100k covariance matrix (~80 GB float64) that the JOSS paper benchmark shows yields only 3–8% WRMSSE improvement at higher aggregation levels (Olivares, Garza & Canseco 2023, *JOSS* 8(84)).

**v0.2+ candidates** (documented, NOT v0.1):

- **NHITS** (Challu et al. 2023, *AAAI*) — 50× faster than Transformer-based at comparable accuracy
- **Temporal Fusion Transformer** (Lim, Arık, Loeff & Pfister 2021, *IJF* 37(4), 1748–1764) — interpretable attention
- **DeepAR** (Salinas, Flunkert, Gasthaus & Januschowski 2020, *IJF* 36(3), 1181–1191) — needs hundreds of related series to shine; defer until v0.2
- **MinT with shrinkage** (see above) — covariance estimator note above
- **ADIDA** (Nikolopoulos et al. 2011, *JORS* 62(3)) — for very-extreme intermittence (>90% zero periods)
- **iETS** (Svetunkov & Boylan 2023, *IJPE*) — unified occurrence + demand-size likelihood; monitor accumulating citations
- **Probabilistic reconciliation** (Panagiotelis et al. 2023, *EJOR* 306(2), 693–706) — full distributions not just quantiles
- **Copula-based bottom-up** (Ben Taieb et al. 2017, *AAAI*; 2020) — preserves cross-series dependence
- **Syntetos-Boylan method classifier** (ADI × CV² grid) — see §13 roadmap

## 6. v0.1 inventory-policy methods

The F2S-minimal core. All policies emit **probabilistic decision artifacts** consuming probabilistic forecast inputs — no point-forecast collapse anywhere on the boundary.

| Policy | Use case | Reference |
|---|---|---|
| **Newsvendor** | Single-period perishable / short-cycle | Silver, Pyke & Peterson (1998) ch. 9; Zipkin (2000) ch. 9 |
| **(Q,R) continuous review** | Steady-volume, continuous monitoring | Silver, Pyke & Peterson (1998) ch. 7 |
| **(s,S) periodic review** *(per-echelon, independent safety stock for multi-echelon)* | Multi-echelon, batched ordering | Zipkin (2000) ch. 9–10 |
| **Base-stock** | Single-echelon, lost-sales or backorder | Zipkin (2000) ch. 6 |
| **PIR generation** | Planned Independent Requirements time-series feeding MRP-equivalent downstream | NEO F2S `S082` Demand Management reference |

**Safety stock — dual mode:**

| Mode | Formula | When |
|---|---|---|
| **Cycle-service-level (CSL)** *(v0.1 default)* | `SS = z_α · σ_LTD` where `σ_LTD` is lead-time-demand std from forecast quantiles | Standard for discrete manufacturing distribution (95% / 97.5% / 99% per ABC class) |
| **Fill-rate (UFR)** | `E[BO] / Q` per Silver-Pyke-Peterson §7.4.2 | Operationally more meaningful; many customer engagements negotiate on fill-rate not CSL |

Selectable via `service_level_type: Literal["csl", "fill_rate"]` config on `InventoryPolicy`. Both modes computed in `inventory_policy/safety_stock.py`.

**Censored estimation references** (for stockout-handling in `estimation/` module):

- Nahmias (1994), "Demand Estimation in Lost Sales Inventory Systems," *Naval Research Logistics* 41(6), 739–757
- **Huh, W.T. & Rusmevichientong, P. (2009)**, "A Nonparametric Asymptotic Analysis of Inventory Planning with Censored Demand," *Mathematics of Operations Research* 34(1), 103–123
- **Sachs, A.-L. & Minner, S. (2014)**, "The Data-Driven Newsvendor with Censored Demand Observations," *International Journal of Production Economics* 149, 28–36

**v0.2 inventory-policy items** (NOT v0.1):

- **Graves-Willems optimal multi-echelon allocation** (Graves & Willems 2000, *M&SOM* 2(1), 68–83) — requires network-topology config that is customer-specific; fails v0.1 config-only test. Per-echelon independent (s,S) handles multi-echelon at v0.1.
- **Service-level-aware joint optimization** — coupled safety-stock + reorder-point optimization
- **Periodic-review base-stock (R,S)** — derivable from (s,S) parameters at v0.1; standalone v0.2

## 7. Interfaces — the contract surface

See `contracts/CONTRACTS.md` for the full schema specification. Summary:

**Feeders** (who feeds DemandSignalOS):

- **Order2Cash_os** → transactional history with explicit `CensoringFlag` via three-tier adapter (heuristic at ingestion → stockout logging → native flag, see CONTRACTS §2.1)
- **External** → POS, weather, calendar, promotion, events as side-feature tables
- **LitReview OS** → research-derived covariates (optional)
- **AlgoTrade data infra** → macro / commodity / FX signals for upstream cost-driver context (reused, not forked)

**Consumers** (who consumes DemandSignalOS):

- **SimOS DES** → probabilistic per-SKU-per-location-per-bucket distributions (quantiles via aligned distribution enum: `normal`, `lognormal`, `exponential`, `empirical`, `fixed`, `uniform`, `triangular`); inventory policies expressed as `(Q,R)`/`(s,S)` decision rules per SKU. Bulk-query interface (function under v0.1 library; REST endpoint v0.1.5+).
- **PlanningOS SD** → aggregated flow curves (family/region/month) with uncertainty bands
- **Order2Cash_os** → near-term order-intake expectations + service-level targets + reorder triggers
- **Closed-loop critic v2** → `ForecastAccuracy` with drift_magnitude + baseline_crps + forecast_horizon_remaining + forecast_horizon_label; **pulled** by the critic on its own cadence (not pushed)

## 8. Architecture sketch

```
platforms_os/
  packages/                   ← shared infrastructure (distinct from platforms)
    ops_schemas/              ← PROMOTION TARGET (S1 — see promotion policy below)
      __init__.py
      demand.py               ← SKU, Location, TimeBucket, DemandActual, CensoringFlag, DemandSignal
      forecast.py             ← ForecastBundle, Quantiles, ProbabilisticDistribution, ForecastProvenance
      policy.py               ← InventoryPolicy (discriminated union), ReorderTrigger, PIR
      accuracy.py             ← ForecastAccuracy
      hierarchy.py            ← SKU/Location hierarchy types
      fallback.py             ← ForecastFallbackStrategy
  Demand_Signal_OS/           ← this repo
    docs/
      CONSTITUTION.md         ← this file
      F2S_BOUNDARY.md         ← in/out scope vs NEO F2S
      BACKTESTING.md          ← M5-aligned protocol
      contracts/
        CONTRACTS.md          ← full schema spec
    forecasting/              ← Nixtla wrap (§10)
      ets.py                  ← AutoETS wrapper
      intermittent/           ← CrostonOptimized, TSB, CrostonSBA
      gbm/                    ← SklearnModel wrapping LightGBM quantile
      reconciliation/         ← BottomUp wrapper (MinT v0.2)
    estimation/               ← NEW sibling module (U7 — breaks circular dep)
      lead_time.py            ← lead-time distribution estimation
      censoring.py            ← three-tier censoring adapter
    inventory_policy/         ← custom (NOT in Nixtla)
      newsvendor.py
      qr.py
      ss.py                   ← per-echelon (s,S)
      base_stock.py
      pir.py
      safety_stock.py         ← CSL + fill-rate modes
    backtest/                 ← custom walk-forward + WIS + WRMSSE
      harness.py
      metrics.py
      benchmarks.py           ← naïve seasonal, SES, MA
    consumers/
      simos_adapter.py        ← in-process orchestration (R-4 — library function, not HTTP)
      planning_adapter.py
      o2c_adapter.py
    config/
      archetypes/
        discrete_manufacturing_distribution.yaml
    tests/
```

**`ops_schemas` promotion policy — ✅ PROMOTION COMPLETED (Phase C, 2026-06-08).**

> **SUPERSEDED:** the promotion below has SHIPPED. `ops_schemas` now lives at `platforms_os/packages/ops_schemas/` (pydantic-only, `py.typed`); DemandSignalOS, PlanningOS, and others import from there. The deferred-nested approach documented here is historical (kept for rationale).

- **v0.1 default (historical):** `ops_schemas/` lived nested inside this repo as
  `demand_signal_os.ops_schemas`. No external consumer imported these
  types yet, so the nested form had zero cost.
- **Promotion trigger:** the first SimOS-side or PlanningOS-side line
  that does `from demand_signal_os.ops_schemas import ...`. At that
  point the transitive-dependency cost (scipy / lightgbm / pandas)
  lands on the consumer for no business-logic reason — that's the
  signal to extract.
- **Promotion target:** `platforms_os/packages/ops_schemas/`. Shared
  infrastructure lives under `packages/`, distinct from platforms
  (`simulation_os/`, `Planning_os/`, etc.) at the top level.
- **Promotion mechanics:** move the 6 modules + rename imports across
  all consumers in one PR. No API change. Estimated ~30 minutes.

**Library-first design rules (v0.1)** — load-bearing per R-5 from architect Round 2. These rules ensure v0.1.5 API extraction is a *deployment*, not a *rewrite*:

1. **Serializable state** — every component of the forecasting pipeline must be serializable to/from dict (Pydantic model or equivalent). No in-memory-only caches, no un-pickleable closures, no thread-local state that can't be reconstructed from (config, seed).
2. **No blocking I/O in forecast computation** — the forecast path (`historical data → ForecastBundle`) must be a pure function of (data, config, seed). File I/O, network calls, database queries happen BEFORE the computation path, not during it. Enables future async-worker extraction.
3. **Config-loadable from YAML or dict** — all configuration (methods, hierarchies, service levels, lead times, ABC classes) loadable from a dict/YAML source. NOT only from Python imports. Enables future API deployment where config comes from a database or environment.

**Deployment topology** (documented for v0.1.5 extraction, not built in v0.1):

- **Async training worker** (Celery / arq / dedicated process) runs the forecast pipeline on a schedule (nightly operational/tactical, weekly strategic)
- **Sync serving API** (FastAPI on port 8006) reads pre-computed forecasts from a database/cache
- **Storage**: PostgreSQL for metadata + `ForecastBundle` records; object store for model artifacts; in-memory cache for hot-path serving
- This is the standard production forecasting-system pattern. The three library-first design rules above are what make this topology extraction possible without rewriting the engine.

## 9. Non-negotiable disciplines

These are the rules that protect the engine from becoming a customization swamp.

1. **No customer-specific code in `inventory_policy/` or `forecasting/`.** All customer variation is config. PR-review rule.
2. **Every policy or forecast method must cite a textbook/paper reference** in code-level docstrings and `docs/`. If you can't cite it, it's not generalizable — it's a customer fit dressed up as math.
3. **Probabilistic outputs end-to-end.** No point-forecast collapse at any internal boundary. Consumers may choose to use only the mean (their decision); the engine emits full quantiles always.
4. **Reproducibility is load-bearing.** Seeded RNG, versioned models, walk-forward backtest with frozen historical cuts. Every forecast bundle carries provenance (`model_id`, `commit_sha`, `seed`, `feature_set_hash`, `data_cut_timestamp`).
5. **Stockout-censoring honesty.** Zero sales is NEVER silently treated as zero demand. `CensoringFlag` is required on every actual, via the three-tier adapter strategy (CONTRACTS §2.1).
6. **Contracts before engine.** No forecasting code merges until the schema contracts (CONTRACTS.md) are reviewed and approved.
7. **No productization without `DECISIONS_LOG` entry.** DemandSignalOS is internal-engine + lighthouse-feeder. Any pressure to ship as a self-serve SKU requires an explicit founder-approved entry in `commercialization/DECISIONS_LOG.md`. The internal pressure to productize will be strong if forecasts are demonstrably better than YAML stopgaps — this rule keeps the decision a conscious one, not a drift.

## 10. Wrap vs. build — Nixtla as v0.1 forecasting backend

**Decision (D2):** v0.1 wraps Nixtla's open-source forecasting stack rather than reimplementing the methods from scratch. Saves ~60–70% of forecasting implementation effort with no contract-surface impact.

| Package | Pinned version | License | Citation |
|---|---|---|---|
| **`statsforecast`** | 2.0.3 | Apache 2.0 | Garza, F., Canseco, M.M. & Olivares, K.G. (2022), *StatsForecast: Lightning fast forecasting with statistical and econometric models*, Zenodo: 10.5281/zenodo.7738325 |
| **`hierarchicalforecast`** | 1.5.1 | Apache 2.0 | Olivares, K.G., Garza, F. & Canseco, M.M. (2022), *HierarchicalForecast: A Python framework for hierarchical forecasting*, Zenodo: 10.5281/zenodo.7738325 |
| **JOSS reference** | — | — | Olivares, K.G., Garza, F. & Canseco, M.M. (2023), "Hierarchical forecasting with Nixtla," *JOSS* 8(84), 5233 |

**Verified Nixtla coverage** (against installed package source, per litreview Round 2):

| DemandSignalOS need | Nixtla class | Notes |
|---|---|---|
| ETS | `AutoETS` | Auto-selection, configurable season_length, damped |
| Croston (optimized) | `CrostonOptimized` | MLE α — default Croston variant for v0.1 |
| Croston (classic) | `CrostonClassic` | α=0.1 fixed — fallback variant |
| TSB | `TSB` | Separate `alpha_d` + `alpha_p` — canonical Teunter-Syntetos-Babai 2011 |
| SBA | `CrostonSBA` | Croston × 0.95 debiasing per Syntetos-Boylan 2005 |
| Gradient boosting | `SklearnModel` (wraps LightGBM quantile) | sklearn-compatible |
| Bottom-up reconciliation | `BottomUp` | v0.1 default |
| MinT with shrinkage | `MinTrace(method='mint_shrink')` | v0.2 stretch — Schäfer-Strimmer covariance estimator |

**Custom code (NOT in Nixtla, must implement):**

- Stockout-censored estimation (in `estimation/censoring.py`)
- Inventory-policy math (in `inventory_policy/`)
- PIR generation (in `inventory_policy/pir.py`)
- Walk-forward backtesting harness (in `backtest/`)
- WIS metric (in `backtest/metrics.py` — ~50 lines)
- API surface (in `api/`, v0.1.5+ only)
- `ForecastFallbackStrategy` implementation (in `forecasting/fallback.py`, contract exists in v0.1)
- Adapter protocol (in `forecasting/protocol.py`) — `ForecastMethod` interface that wraps Nixtla but enables future backend swap without contract-surface change

**Vendor-lock-in risk: LOW.** The wrap boundary is the `ForecastBundle` contract. The `method` field is a string identifier ("ets" | "croston_opt" | "tsb" | "sba" | "gbm"), not a Nixtla import. If Nixtla becomes problematic, only the forecasting backend swaps — custom code (censoring, policy, API, backtest) is unaffected.

## 11. Build sequencing — library-first v0.1, API v0.1.5

**Decision (D1):** v0.1 ships as a Python library (no port 8006, no Docker image, no REST API, no database). API extraction deferred to v0.1.5 only after the library has proven value against the existing PlanningOS↔SimOS closed loop.

**Rationale:**

- PlanningOS already runs on YAML-based demand priors. DemandSignalOS should earn its port by proving it adds value before committing to deployment infrastructure.
- Library-first defers ~3 days of infra work (Dockerfile, DB schema, REST endpoints, health checks, auth) and reduces SimOS-side integration from ~200 lines + infra to ~160 lines no infra (per simos Round 2 estimate).
- The closed-loop critic v2 extension lives in PlanningOS; DemandSignalOS emits `ForecastAccuracy` on-demand via library calls.
- The three library-first design rules (§8) prevent the future extraction from being a rewrite.

**4-phase plan:**

```
Phase 1 — DemandSignalOS v0.1 library (1–2 weeks)
  ├─ ops_schemas nested at demand_signal_os.ops_schemas
  │   (promotion to platforms_os/packages/ops_schemas/ deferred
  │    until first SimOS / PlanningOS import — see §8 policy)
  ├─ forecasting/ — wrap Nixtla (ETS, CrostonOptimized, TSB, CrostonSBA, GBM)
  ├─ inventory_policy/ — custom (newsvendor, QR, sS, base-stock, PIR, safety-stock CSL + fill-rate)
  ├─ estimation/ — lead-time + censoring three-tier adapter
  ├─ reconciliation/ — BottomUp (Nixtla)
  ├─ backtest/ — walk-forward + CRPS + sMAPE + WRMSSE + WIS + benchmarks
  ├─ consumers/simos_adapter.py — in-process orchestration
  └─ Unit tests + synthetic-data fixture

Phase 2 — SimOS integration (~160 lines, ~2 days; parallelizable with Phase 1)
  ├─ SimOS-side: add distribution_override to ArrivalConfig + loader.py (~50 lines) ← BLOCKING
  ├─ SimOS-side: add DemandForecastDistribution to distributions/ (~40 lines)
  ├─ DemandSignalOS-side: consumers/simos_adapter.py (~80 lines)
  └─ PlanningOS-side: wire adapter into closed_loop/exporter.py (~10 lines)

Phase 3 — Closed-loop critic v2 (~30 lines, half day)
  ├─ Add drift_detected detector to PlanningOS critic/archetypes.py
  └─ Wire ForecastAccuracy into orchestrator's iteration record

Phase 4 — v0.1.5 standalone API extraction (deferred — earned, not assumed)
  ├─ Trigger criterion: v0.1 library proven against real Planning2Cash loop
  ├─ REST API on port 8006
  ├─ Docker image + DB schema + health endpoints
  ├─ ForecastFallbackStrategy implementation (contract exists in v0.1)
  └─ Syntetos-Boylan DemandClassifier (§13 roadmap)
```

**SimOS-side prerequisite** (Phase 2 blocker): a separate feature branch in `simulation_os/` adds `distribution_override: Distribution | None = None` to `ArrivalConfig` and `build_simulation()`. Backward-compatible. Without it, DemandSignalOS cannot inject forecast-derived distributions into SimOS scenarios. This must be coordinated separately, NOT inside `Demand_Signal_OS/`.

## 12. Open questions — RESOLVED in v0.1 draft

The v0 draft carried five open questions. After Round 1 + Round 2 MAO triangulation, all are resolved:

| Q | v0 question | v0.1 resolution |
|---|---|---|
| Q1 | `ops_schemas` location | **Nested at `demand_signal_os.ops_schemas` for v0.1 (YAGNI); promote to `platforms_os/packages/ops_schemas/` at first external consumer import.** See §8 promotion policy. The transitive-dependency cost (scipy / lightgbm / pandas) is the real trigger, not the reverse-dependency aesthetic. |
| Q2 | Third forecasting method (GBM vs probabilistic DL) | **GBM via Nixtla `SklearnModel` wrapping LightGBM quantile** — explainable (SHAP), no GPU dependency, lower data requirements than DeepAR |
| Q3 | MinT realism for v0.1 | **Bottom-up = v0.1 default. MinT with Schäfer-Strimmer shrinkage = v0.2 stretch** — at 10k+ SKU scale MinT yields only 3–8% WRMSSE improvement at higher aggregation per JOSS benchmark |
| Q4 | Where actuals_drift signal lives | **In PlanningOS critic (extends Phase-7 verdict schema). DemandSignalOS emits `ForecastAccuracy` on demand (pull, not push)** — keeps coupling one-directional |
| Q5 | `demand_signal_consultant` MAO agent at launch | **Defer to v0.2** when multi-echelon allocation (Graves-Willems) and DemandClassifier are in scope |

## 13. v0.1.5 / v0.2 roadmap

Items deferred from v0.1 with founder-approved triggers:

| Item | Trigger | Reference |
|---|---|---|
| **REST API extraction (port 8006)** | v0.1 library proves value against real Planning2Cash loop | §11 Phase 4 |
| **MinT with Schäfer-Strimmer shrinkage** | Sustained need for top-level forecast accuracy beyond bottom-up | §5; Olivares-Garza-Canseco 2023 JOSS |
| **`ForecastFallbackStrategy` implementation** | Cold-start / NPI / promo / discontinued / new-location cases hit in dogfooding (contract exists in v0.1) | CONTRACTS §1 |
| **Syntetos-Boylan demand classifier** *(new in v0.1.5/v0.2 per litreview R2)* | Manual method selection becomes a friction point. ADI × CV² grid auto-routes SKUs to methods (smooth→ETS, intermittent→CrostonSBA, lumpy→TSB). ~100 lines, `classification/` sibling module | Syntetos & Boylan (2005), *IJF* 21(2) |
| **Graves-Willems optimal multi-echelon allocation** | Customer engagement requires joint multi-echelon optimization (per-echelon (s,S) handles v0.1 needs) | Graves & Willems (2000), *M&SOM* 2(1), 68–83 |
| **Probabilistic deep learning** (DeepAR, N-BEATS, NHITS, TFT) | Forecast accuracy gap vs. GBM justifies GPU dependency | §5 v0.2+ candidates |
| **WIS in `ForecastAccuracy` schema** | First external consumer requests WIS as part of accuracy reporting (implemented as backtest metric in v0.1) | §5 BACKTESTING.md |
| **Probabilistic reconciliation** (Panagiotelis et al. 2023) | Cross-quantile coherence beyond per-quantile reconciliation needed | §5 v0.2+ candidates |
| **Adjacent archetypes** — pharma / fashion / grocery / automotive | Real customer engagement in archetype OR Planning2Cash dogfooding hits archetype-specific need | §4 |
| **Minimum quantile-band guard** *(new from D5 UAT-1b finding, 2026-06-08)* | Forecast methods (ETS in particular) produce degenerate quantile bands on near-noiseless inputs — `q95 − q05 ≈ 0`. Statistically correct (zero observed variance → zero predicted variance) but downstream `safety_stock = z · σ_LTD` collapses to 0, the closed-loop critic loses its `drift_magnitude` signal, and `(Q,R)` reorder point drops the protection buffer. Trigger to ship: first customer demo on stylized/noiseless data OR an integration test that exposes the gap. Recommended implementation: add an optional `min_quantile_spread` config knob per `ForecastMethod` (and a global default in archetype YAML); when innovation variance falls below the threshold, enforce a configurable floor on the emitted band — standard regularization practice in IBP vendor implementations. Practitioner impact on real (noisy) data is low — flagged here so the gap doesn't surface during a demo. | D5 UAT-1b (UAT report 2026-06-08); CONTRACTS §1.3 `Quantiles` |

## 14. Relation to locked strategy

This platform is **internal-engine + lighthouse-feeder**, not a new commercial surface. It does not contradict:

- `DECISIONS_LOG §M #50–53` (sim-os.ai canopy + agents/supplychain subdomains + PlanningOS at `/planning/*` Enterprise-gated) — DemandSignalOS sits behind the Enterprise tier, surfaced to customers only as decision artifacts inside engagements, never as a self-serve SKU.
- `DECISIONS_LOG §E #19-a` / `#18-a/b/c` (every commerce surface leads with decision answer in practitioner units) — DemandSignalOS outputs decisions (forecasts, reorder triggers, safety stocks), not engine access.
- `DECISIONS_LOG §K #32–#45` (MAO PaaS JV scope-isolated) — DemandSignalOS is Founder-A 100% solo per `#1`, not in JV scope.
- `STRATEGIC_BASELINE.md` — extends the trio (O2C + SimOS + MAO) with a forecasting leg necessary for Planning2Cash dogfooding and Enterprise lighthouse case-study generation.

The locked Enterprise Tier commerce model maps cleanly:

- **Engine** = product (this repo) → defensible, scalable, generalizable
- **Operational fit** = engagement (Enterprise tier consulting) → customer-specific work

## 15. Revision history

| Version | Date | Notes |
|---|---|---|
| **v0** | 2026-06-08 | Founding draft on `feat/founding-design`. Three documents committed at root-commit `f4ab4b3` |
| **v0.1** | 2026-06-08 | Two-round MAO triangulation applied. 16 Round-1 revisions + 7 Round-2 refinements integrated. All 5 v0 open questions resolved. Nixtla wrap adopted. Library-first sequencing locked. |
| **Phase 1** | 2026-06-08 | Library skeleton — `ops_schemas` spine, 5 forecasting wrappers (Nixtla-based), 5 inventory-policy modules, `estimation/` sibling, backtest harness + WIS + 3 benchmarks, `consumers/simos_adapter.py`. 65 tests + ruff + mypy strict clean. |
| **Phase 3** | 2026-06-08 | DSO `accuracy.evaluate()` producer + closed-loop critic integration (consumed by PlanningOS critic's `drift_detected` archetype). Cross-repo E2E 4/4. |
| **Phase A** | 2026-06-08 | `min_quantile_spread` band-width guard resolves the D5 UAT-1b finding. All 5 forecast methods honor the floor; q50 preserved; noisy input untouched. 13 unit + 7/7 UAT. |
| **Phase B + B.1** | 2026-06-08 | `consumers/simos_arrivals_adapter.py` — DSO emits SimOS-compatible `arrivals.schedule` from `ForecastBundle` records. Robustness pass: NaN/inf loud-fail, negative mean clipped, `noise_std` capped at `rate/3` so SimOS cannot draw negative arrivals. 21 unit tests. |
| **Phase C (DSO side)** | 2026-06-08 | `ops_schemas/*` becomes thin re-export shim from the promoted `platforms_os/packages/ops_schemas/` package. Backward-compatible: every pre-existing `from demand_signal_os.ops_schemas import ...` keeps working. New consumers (PlanningOS production wire-up) import the lighter shared package directly. DSO ships `py.typed` marker. |
| **Phase E** | 2026-06-08 | Cross-repo E2E + adversarial UAT 8/8 PASS — drives the full Planning2Cash production loop through the FastAPI endpoint with real DSO ETS + real critic + real `drift_detected` halt at drift=5.50× baseline_crps. Adversarial inputs at every contract seam survive (NaN/inf/negative on all of accuracy / arrivals / band guard / provider; DSO exceptions; malformed API config). |
