# DemandSignalOS — CONSTITUTION

> Probabilistic demand signal engine for the Planning2Cash internal playground.
> Forecast honestly. Reconcile hierarchically. Hand probabilistic outputs to every downstream consumer without information loss.

**Status:** v0 founding draft (2026-06-08) on branch `feat/founding-design`. Pending MAO triangulation + founder approval.

**Repo:** `github.com/nguyenhoangthangbt/Demand_Signal_OS` — sibling to `simulation_os/`, `Planning_os/`, `AlgoTrade_os/`, `LitReview_os/`, `Analytic_os/`. Cloned under `platforms_os/Demand_Signal_OS/`.

**Port slot:** 8006 (next after AlgoTrade 8005).

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
- **Backtesting harness** — walk-forward, out-of-sample, cost-aware evaluation (service-level vs. holding-cost vs. stockout-cost tradeoff curves).
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
| Distinguishing math | Croston/TSB for intermittents, (s,S) for multi-echelon DC, hierarchical reconciliation |
| Rationale | Closest archetype to existing O2C lighthouse domain; cleanest test against SimOS DES + PlanningOS SD |

Adjacent archetypes documented as roadmap layers, not v0.1 surface:

- **Pharma / regulated** — shelf-life-constrained newsvendor, batch tracking (v0.3+)
- **Fashion / short-cycle** — analog-based NPI, fast/slow-mover splits (v0.3+)
- **Grocery / FMCG** — daily-reorder, promo uplift dominant (v0.4+)
- **Automotive / OEM** — MRP, BOM-coupled (v0.5+)

## 5. v0.1 forecasting methods

Three methods, chosen for orthogonal coverage and explainability:

| Method | Why | Reference |
|---|---|---|
| **ETS** (Error-Trend-Seasonal state-space) | Seasonal, steady-volume series. Probabilistic via state-space innovations. | Hyndman & Athanasopoulos, *Forecasting: Principles and Practice* (3rd ed.) |
| **Croston / TSB** | Intermittent demand. Decomposes inter-demand intervals from demand sizes. | Croston 1972; Teunter-Syntetos-Babai 2011 (TSB) |
| **Gradient-boosting with calendar + promo + lag features** | Explainable, non-linear, multivariate. Quantile loss for probabilistic outputs. | Hyndman & Athanasopoulos ch. 12; LightGBM quantile regression |

**Hierarchical reconciliation:** MinT (Minimum Trace, Wickramasuriya-Athanasopoulos-Hyndman 2019) over the SKU → family → total + location → region → total hierarchies. Bottom-up reconciliation as v0.1 fallback if MinT covariance estimation is unstable.

**v0.2+ candidates** (documented, not v0.1): N-BEATS, NHITS, Temporal Fusion Transformer (Lim et al. 2021), DeepAR (Salinas et al. 2020).

## 6. v0.1 inventory-policy methods

The F2S-minimal core. All policies emit **probabilistic decision artifacts** consuming probabilistic forecast inputs — no point-forecast collapse anywhere on the boundary.

| Policy | Use case | Reference |
|---|---|---|
| **Newsvendor** | Single-period perishable / short-cycle | Silver-Pyke-Peterson; Zipkin ch. 9 |
| **(Q,R) continuous review** | Steady-volume, continuous monitoring | Silver-Pyke-Peterson ch. 7 |
| **(s,S) periodic review** | Multi-echelon, batched ordering | Zipkin ch. 9–10 |
| **Base-stock** | Single-echelon, lost-sales or backorder | Zipkin ch. 6 |
| **PIR generation** | Planned Independent Requirements time-series feeding MRP-equivalent downstream | NEO F2S `S082` Demand Management reference |

Safety stock: `SS = z_α · σ_LTD` where `σ_LTD` is the standard deviation of lead-time demand (computed from the forecast quantiles, not from point forecasts).

## 7. Interfaces — the contract surface

See `contracts/CONTRACTS.md` for the full schema specification. Summary:

**Feeders** (who feeds DemandSignalOS):

- **Order2Cash_os** → transactional history with explicit `CensoringFlag` (zero = real-zero vs. stockout-censored)
- **External** → POS, weather, calendar, promotion, events as side-feature tables
- **LitReview OS** → research-derived covariates (optional)
- **AlgoTrade data infra** → macro / commodity / FX signals for upstream cost-driver context (reused, not forked)

**Consumers** (who consumes DemandSignalOS):

- **SimOS DES** → probabilistic per-SKU-per-location-per-bucket distributions (quantiles or distribution params); inventory policies expressed as `(Q,R)`/`(s,S)` decision rules per SKU
- **PlanningOS SD** → aggregated flow curves (family/region/month) with uncertainty bands
- **Order2Cash_os** → near-term order-intake expectations + service-level targets + reorder triggers
- **Closed-loop critic v2** → forecast accuracy actuals-vs-predicted as a third signal source for the Phase-7 critic

## 8. Architecture sketch

```
Demand_Signal_OS/
  docs/
    CONSTITUTION.md           ← this file
    F2S_BOUNDARY.md           ← in/out scope vs NEO F2S
    contracts/
      CONTRACTS.md            ← full schema spec
  ops_schemas/                 ← shared types (extends platforms_os ops_schemas)
    demand.py                 ← DemandSignal, DemandActual, CensoringFlag
    forecast.py               ← ForecastBundle, Quantiles, ProbabilisticDistribution
    policy.py                 ← InventoryPolicy, ReorderTrigger, PIR
    hierarchy.py              ← SKU/Location hierarchy, reconciliation contracts
  forecasting/
    ets/                      ← state-space ETS
    intermittent/             ← Croston, TSB
    gbm/                      ← gradient-boosting with covariates
    reconciliation/           ← MinT + bottom-up
    backtest/                 ← walk-forward harness
  inventory_policy/
    newsvendor.py
    qr.py                     ← (Q,R) continuous review
    ss.py                     ← (s,S) periodic review
    base_stock.py
    pir.py                    ← PIR generation
    safety_stock.py           ← z·σ_LTD given probabilistic input
  api/                        ← REST endpoints on port 8006
    forecasts.py
    policies.py
    health.py
  config/
    archetypes/
      discrete_manufacturing_distribution.yaml
  tests/
    forecasting/
    inventory_policy/
    integration/              ← end-to-end loop tests
  CLAUDE.md                   ← dev guide for this repo
```

## 9. Non-negotiable disciplines

These are the rules that protect the engine from becoming a customization swamp.

1. **No customer-specific code in `inventory_policy/` or `forecasting/`.** All customer variation is config. PR-review rule.
2. **Every policy or forecast method must cite a textbook/paper reference** in code-level docstrings and `docs/`. If you can't cite it, it's not generalizable — it's a customer fit dressed up as math.
3. **Probabilistic outputs end-to-end.** No point-forecast collapse at any internal boundary. Consumers may choose to use only the mean (their decision); the engine emits full quantiles always.
4. **Reproducibility is load-bearing.** Seeded RNG, versioned models, walk-forward backtest with frozen historical cuts. Every forecast bundle carries provenance (`model_id`, `commit_sha`, `seed`, `feature_set_hash`, `data_cut_timestamp`).
5. **Stockout-censoring honesty.** Zero sales is NEVER silently treated as zero demand. `CensoringFlag` is required on every actual.
6. **Contracts before engine.** No forecasting code merges until the schema contracts (CONTRACTS.md) are reviewed and approved. The 2026-06-08 founder rule: "build engine v0.1 AFTER the three founding documents are signed off."

## 10. What lives WHERE

| Concern | Location | Why |
|---|---|---|
| Forecasting + inventory-policy math | `Demand_Signal_OS/` (this repo) | Generalizable engine — build once, deploy across customers |
| Strategic SD flows | `Planning_os/` | Existing — orthogonal scope |
| Tactical DES | `simulation_os/` | Existing — orthogonal scope |
| Transactional O2C | `0NEO/6-Order2Cash_os/` | Spun out — commercial scope |
| Operational F2S (substitution, supersession, batch, quality, DC-to-DC, etc.) | Future `0NEO/F2S_os/` | Reserved — commercial scope, customer-specific |
| Planning2Cash orchestration | `platforms_os/planning2cash/` (future, thin) | Orchestrator only, not a platform |
| MAO agent for end-to-end loop | `master_agents_os/examples/planning2cash_runner.yaml` (future) | One agent drives the loop |

## 11. Relation to locked strategy

This platform is **internal-engine + lighthouse-feeder**, not a new commercial surface. It does not contradict:

- `DECISIONS_LOG §M #50–53` (sim-os.ai canopy + agents/supplychain subdomains + PlanningOS at `/planning/*` Enterprise-gated) — DemandSignalOS sits behind the Enterprise tier, surfaced to customers only as decision artifacts inside engagements, never as a self-serve SKU.
- `DECISIONS_LOG §E #19-a` / `#18-a/b/c` (every commerce surface leads with decision answer in practitioner units) — DemandSignalOS outputs decisions (forecasts, reorder triggers, safety stocks), not engine access.
- `DECISIONS_LOG §K #32–#45` (MAO PaaS JV scope-isolated) — DemandSignalOS is Founder-A 100% solo per `#1`, not in JV scope.
- `STRATEGIC_BASELINE.md` — extends the trio (O2C + SimOS + MAO) with a forecasting leg necessary for Planning2Cash dogfooding and Enterprise lighthouse case-study generation.

The locked Enterprise Tier commerce model maps cleanly:

- **Engine** = product (this repo) → defensible, scalable, generalizable
- **Operational fit** = engagement (Enterprise tier consulting) → customer-specific work

## 12. Open questions for MAO triangulation

These are the deliberate ambiguities the founding draft does not resolve, reserved for MAO triangulation in this session:

1. Should `ops_schemas` (the shared types) live in `Demand_Signal_OS/`, or be promoted to a top-level shared package consumed by all platforms?
2. Is `gradient-boosting with covariates` the right third forecasting method, or should v0.1 favor a probabilistic deep-learning method (DeepAR / Temporal Fusion Transformer)?
3. Is MinT hierarchical reconciliation realistic for v0.1, or should bottom-up suffice until covariance estimation is proven?
4. Should the closed-loop critic (Phase-7) extension to include `actuals_drift` live in DemandSignalOS or PlanningOS?
5. Does `inventory_policy/` warrant its own MAO consultant agent (`demand_signal_consultant`?) at launch, or wait until v0.2?
