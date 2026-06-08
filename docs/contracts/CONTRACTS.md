# CONTRACTS — DemandSignalOS schema surface

> Contracts before engine. Every feeder and consumer relationship is specified here BEFORE any forecasting or inventory-policy code is merged.

**Status:** v0.1 (2026-06-08) on branch `feat/founding-design`. Round 1 + Round 2 MAO triangulation applied. All open questions resolved.

**Companion documents:** `../CONSTITUTION.md`, `../F2S_BOUNDARY.md`, `../BACKTESTING.md`.

---

## 0. Reading map

- §1 — Type primitives (nested at `demand_signal_os.ops_schemas` for v0.1; promotion target `platforms_os/packages/ops_schemas/` — see CONSTITUTION §8)
- §2 — Feeder contracts (signals INTO DemandSignalOS)
- §3 — Consumer contracts (signals OUT of DemandSignalOS)
- §4 — Internal contract: forecasting → inventory_policy (with `estimation/` sibling)
- §5 — Hierarchical reconciliation contract
- §6 — Provenance + reproducibility contract
- §7 — Versioning + evolution
- §8 — `ForecastFallbackStrategy` cold-start / NPI / promo / discontinued primitive
- §9 — Internal seam enforcement
- §10 — Observability (minimal)
- §11 — Failure modes (basic)
- §12 — Security (decision-documented)

---

## 1. Type primitives — shared package surface

**Location policy** (per CONSTITUTION §8):

- **v0.1 (now):** types live nested inside this repo as `demand_signal_os.ops_schemas`. No external consumer imports them yet; YAGNI rules.
- **Promotion trigger:** first SimOS- or PlanningOS-side import of these types. The transitive-dependency cost (scipy / lightgbm / pandas) on the consumer is the real signal, not the "reverse dependency" aesthetic.
- **Promotion target:** `platforms_os/packages/ops_schemas/`. Shared infrastructure lives under `packages/`, distinct from platforms at the top level.

The schema definitions below are stable across the move — the promotion is mechanical (relocate + rename imports). When promoted, SimOS / PlanningOS / Order2Cash_os import directly from `platforms_os.packages.ops_schemas` without depending on the `demand_signal_os` distribution.

Every top-level artifact carries `schema_version: int` for evolution (per D4).

### 1.1 Identity + hierarchy

```python
class SKU(BaseModel):
    schema_version: int = 1
    sku_id: str
    family_id: str | None = None
    category_id: str | None = None
    abc_class: Literal["A", "B", "C"]
    archetype: ArchetypeTag  # "discrete_mfg" | "pharma" | "fashion" | ...

class Location(BaseModel):
    schema_version: int = 1
    location_id: str
    location_type: Literal["factory", "central_dc", "regional_dc", "store", "vendor"]
    region_id: str | None = None
    parent_location_id: str | None = None  # echelon-up reference

class TimeBucket(BaseModel):
    schema_version: int = 1
    period: Literal["day", "week", "month", "quarter"]
    start: date
    end: date
    timezone: str = "UTC"
```

### 1.2 Demand signal + actual

```python
class CensoringFlag(str, Enum):
    OBSERVED = "observed"              # units_sold > 0 with no stockout
    REAL_ZERO = "real_zero"            # units_sold == 0, in stock all bucket
    STOCKOUT_CENSORED = "stockout_censored"  # zero sales because OOS
    PARTIAL_CENSORED = "partial_censored"    # some demand before mid-bucket OOS
    UNKNOWN = "unknown"                # legacy / source did not flag; exclude

class DemandActual(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    units_sold: float
    units_demanded: float | None = None
    censoring: CensoringFlag
    stockout_duration_hours: float | None = None
    source_system: str
    recorded_at: datetime

class DemandSignal(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    signal_type: Literal["actual", "pos", "promo_flag", "weather", "calendar_event", "macro", "research_covariate"]
    value: float | str | dict
    source_system: str
    provenance_id: str
```

### 1.3 Forecast + distribution

Per S2 + R-1: the `ProbabilisticDistribution.family` enum aligns with SimOS's `distributions/registry.py` natively-supported families. SimOS samples without adapter code:

```python
class Quantiles(BaseModel):
    schema_version: int = 1
    q05: float
    q10: float
    q25: float
    q50: float
    q75: float
    q90: float
    q95: float

class ProbabilisticDistribution(BaseModel):
    schema_version: int = 1
    family: Literal[
        "normal",      # SimOS NormalDistribution
        "lognormal",   # SimOS LognormalDistribution
        "exponential", # SimOS exponential — natural for inter-arrival demand
        "empirical",   # SimOS EmpiricalDistribution — quantile-based
        "fixed",       # SimOS FixedDistribution — degenerate / known constant
        "uniform",     # SimOS UniformDistribution
        "triangular",  # SimOS TriangularDistribution — expert-elicited ranges
    ]
    params: dict  # family-specific parameters
    support: tuple[float, float] | None = None

class ForecastBundle(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    horizon_label: Literal["operational", "tactical", "strategic"]
    quantiles: Quantiles
    distribution: ProbabilisticDistribution | None = None  # for native SimOS sampling
    mean: float
    method: str  # "ets" | "croston_opt" | "tsb" | "sba" | "gbm_q50" | ...
    fallback_applied: ForecastFallbackStrategy | None = None  # see §8
    provenance: ForecastProvenance
```

### 1.4 Inventory policy — discriminated union per `policy_type` (S8)

Per S8 + U3: replace `parameters: dict` with a discriminated union per `policy_type`; add `service_level_type` for CSL-vs-fill-rate selection.

```python
class QRParameters(BaseModel):
    policy_type: Literal["qr"] = "qr"
    Q: float  # order quantity
    R: float  # reorder point

class SSParameters(BaseModel):
    policy_type: Literal["ss"] = "ss"
    s: float  # reorder threshold
    S: float  # order-up-to level
    echelon_index: int = 0  # per-echelon (s,S) — 0 = leaf, N = highest

class BaseStockParameters(BaseModel):
    policy_type: Literal["base_stock"] = "base_stock"
    base_level: float

class NewsvendorParameters(BaseModel):
    policy_type: Literal["newsvendor"] = "newsvendor"
    optimal_quantity: float
    critical_ratio: float

PolicyParameters = Annotated[
    QRParameters | SSParameters | BaseStockParameters | NewsvendorParameters,
    Field(discriminator="policy_type"),
]

class ReorderTrigger(BaseModel):
    schema_version: int = 1
    trigger_type: Literal["below_reorder_point", "periodic_review", "manual"]
    sku_id: str
    location_id: str
    threshold: float | None = None
    review_cadence: str | None = None

class InventoryPolicy(BaseModel):
    schema_version: int = 1
    sku_id: str
    location_id: str
    parameters: PolicyParameters  # discriminated union (S8)
    safety_stock: float
    service_level_target: float
    service_level_type: Literal["csl", "fill_rate"] = "csl"  # U3
    reorder_triggers: list[ReorderTrigger]
    forecast_provenance: ForecastProvenance
    valid_from: datetime
    valid_until: datetime

class PIR(BaseModel):
    """Planned Independent Requirement — for PlanningOS + O2C consumers only (S7).
    SimOS does NOT consume PIRs (samples from ForecastBundle.distribution)."""
    schema_version: int = 1
    sku_id: str
    location_id: str
    bucket: TimeBucket
    quantity_planned: float
    quantiles: Quantiles | None = None  # optional per D5 — ERP consumers expect deterministic
    forecast_provenance: ForecastProvenance
```

### 1.5 Provenance

```python
class ForecastProvenance(BaseModel):
    schema_version: int = 1
    forecast_bundle_id: str
    model_id: str
    commit_sha: str
    seed: int
    feature_set_hash: str
    data_cut_timestamp: datetime
    produced_at: datetime
```

---

## 2. Feeder contracts — signals INTO DemandSignalOS

### 2.1 Order2Cash_os → DemandSignalOS — transactional history with three-tier censoring adapter

Per S4: `CensoringFlag` cannot land natively in O2C today. The three-tier adapter strategy bridges this gap.

**Producer:** `Order2Cash_os` (commercial sibling, currently at `0NEO/6-Order2Cash_os/`).

**Artifact:** stream of `DemandActual` records (§1.2) with `CensoringFlag` resolved via the three-tier adapter.

**Three-tier censoring adapter** (in `estimation/censoring.py`):

| Tier | Status | What |
|---|---|---|
| **Tier 1** | v0.1 — implement | **Heuristic at ingestion.** If `DemandActual` arrives with `CensoringFlag.UNKNOWN` (which all O2C records will be initially), apply: (a) if `units_sold == 0` AND SKU was in stock at bucket start per O2C inventory snapshot → flag `REAL_ZERO`; (b) if `units_sold == 0` AND SKU was out of stock at bucket start → flag `STOCKOUT_CENSORED`; (c) if inventory snapshot unavailable → flag `UNKNOWN` and exclude from training. Lives in DemandSignalOS's ingestion layer, not in O2C. Requires O2C to expose inventory-position snapshots (which it likely has for order fulfillment). |
| **Tier 2** | v0.2 — Order2Cash_os schema migration | **Stockout event logging.** O2C adds a stockout-event table tracking when an SKU went out of stock and for how long. Feeds `DemandActual.stockout_duration_hours`. |
| **Tier 3** | v0.3+ — full native | **Native `CensoringFlag`.** O2C emits `CensoringFlag` directly per record. |

**Censored-estimation references** (literature anchors):

- Nahmias (1994), "Demand Estimation in Lost Sales Inventory Systems," *Naval Research Logistics* 41(6), 739–757
- **Huh, W.T. & Rusmevichientong, P. (2009)**, "A Nonparametric Asymptotic Analysis of Inventory Planning with Censored Demand," *Mathematics of Operations Research* 34(1), 103–123
- **Sachs, A.-L. & Minner, S. (2014)**, "The Data-Driven Newsvendor with Censored Demand Observations," *International Journal of Production Economics* 149, 28–36

(Per U1: Cooper-Homem-de-Mello 2006 — previously cited in v0 — is about revenue management spiral-down, not inventory demand estimation. Replaced.)

**Cadence:**
- Batch nightly for historical training-set refresh
- Streaming (event-driven) for operational-horizon actuals feeding closed-loop critic

**Failure mode:** records with `CensoringFlag.UNKNOWN` after Tier-1 adapter are excluded from training (not silently treated as `REAL_ZERO`). Excluded counts tracked + reported on forecast provenance.

**Function interface (v0.1 library)** — under library-first sequencing per D1, ingestion happens in-process:

```python
def ingest_actuals(records: Iterable[DemandActual]) -> IngestResult
def ingest_actuals_stream(record: DemandActual) -> None
```

REST endpoints (`POST /api/v1/actuals/ingest`, `POST /api/v1/actuals/event`) materialize at v0.1.5.

### 2.2 External sources → DemandSignalOS — covariate signals

**Producer:** various external systems (POS feeds, weather APIs, calendar/holiday tables, promotion calendars, event-schedule sources).

**Artifact:** stream of `DemandSignal` records (§1.2) with `signal_type ∈ {pos, promo_flag, weather, calendar_event}`.

**Cadence:** daily batch for most signals; near-real-time streaming where the source supports it.

**Failure mode:** missing covariates do not block forecasting — they degrade it. The forecasting engine MUST tolerate sparse covariate coverage and report covariate-completeness as a forecast-quality dimension.

**Function interface (v0.1):** `def ingest_signals(records: Iterable[DemandSignal]) -> IngestResult`.

### 2.3 LitReview OS → DemandSignalOS — research-derived covariates (optional)

**Producer:** `LitReview_os/` — research-derived static features (e.g., published demand-elasticity coefficients per product category).

**Artifact:** `DemandSignal` records with `signal_type = "research_covariate"`.

**Cadence:** ad-hoc.

**Failure mode:** entirely optional; absence has no effect on baseline forecasting.

### 2.4 AlgoTrade OS data infra → DemandSignalOS — upstream cost-driver signals

**Producer:** `AlgoTrade_os/` data-ingestion pipelines (commodity prices, FX, macro signals).

**Artifact:** `DemandSignal` records with `signal_type = "macro"`.

**Use case:** v0.2+, for archetypes where demand correlates with upstream cost drivers. **NOT v0.1 surface.**

**Reuse vs. fork:** DemandSignalOS REUSES AlgoTrade's data-pipeline infrastructure (estimated ~40% transferable per CONSTITUTION §3). Does NOT fork.

---

## 3. Consumer contracts — signals OUT of DemandSignalOS

### 3.1 DemandSignalOS → SimOS DES — probabilistic demand distributions

**Consumer:** `simulation_os/` Discrete-Event Simulation engine.

**Artifact:** `ForecastBundle` records (§1.3) with `horizon_label = "operational"` or `"tactical"`, populated `ProbabilisticDistribution` (any family from the aligned 7-family enum), and per-SKU-per-location-per-time-bucket granularity. Plus `InventoryPolicy` records (§1.4) per SKU/location for policy-compliance evaluation.

**Consumption pattern (library-first per D1 + R-4):**

```python
# In SimOS-side or closed-loop exporter (in-process import):
from demand_signal_os.consumers.simos_adapter import (
    forecast_bulk,
    forecast_single,
    DemandForecastDistribution,
)

# Bulk-query interface — replaces v0.1.5 REST bulk endpoint
forecasts: dict[tuple[str, str], ForecastBundle] = forecast_bulk(
    sku_ids=[...], location_ids=[...], horizon="operational",
)

# Per-SKU lookup for interactive use
bundle: ForecastBundle = forecast_single(sku_id, location_id, "operational", bucket)
```

`DemandForecastDistribution` (defined in `consumers/simos_adapter.py`) wraps a `ForecastBundle.quantiles` into a SimOS `Distribution` protocol with linear-interpolation `sample()`. Registered into SimOS's `distributions/registry.py` via `register("demand_forecast", DemandForecastDistribution)`.

**SimOS-side prerequisite** (per simos Round 2 — single blocking change): SimOS `config/loader.py` + `schema.py` adds `distribution_override: Distribution | None = None` to `ArrivalConfig` and `build_simulation()`. ~50 lines. Backward-compatible. Lives in `simulation_os/` repo on a separate feature branch.

**Failure mode:** if no forecast available for a requested (SKU, location, bucket), `forecast_single` returns `None` with `fallback_applied` populated per §8 strategy (or raises `ForecastUnavailable` if strategy is `reject`). SimOS does NOT receive a fabricated fallback.

**REST endpoint** (materializes v0.1.5+): `GET /api/v1/forecasts/bulk?scenario_id=...&horizon=...`.

### 3.2 DemandSignalOS → PlanningOS SD — aggregated flow curves

**Consumer:** `Planning_os/` System Dynamics strategic-planning engine.

**Artifact:** aggregated `ForecastBundle` records with `horizon_label = "strategic"`, aggregated to (family, region, month) or coarser per PlanningOS configuration. Quantiles preserved as uncertainty bands.

**Consumption pattern:** PlanningOS SD uses aggregated forecast curves as exogenous flow inputs. Uncertainty band drives PlanningOS scenario branches.

**Hierarchical reconciliation:** the aggregated curves served to PlanningOS MUST be hierarchically consistent with the per-SKU forecasts served to SimOS. See §5.

**Function interface (v0.1):** `def forecast_aggregated(family_ids, region_ids, period: Literal["month"], horizon="strategic") -> list[ForecastBundle]`. REST endpoint v0.1.5+.

### 3.3 DemandSignalOS → Order2Cash_os — operational decision triggers

**Consumer:** `Order2Cash_os` (commercial sibling).

**Artifact:** `InventoryPolicy` records (§1.4) with active `ReorderTrigger` rules + near-term order-intake expectations (`PIR` records, §1.4).

**Consumption pattern:** Order2Cash_os reads policies + triggers, surfaces reorder recommendations to operations teams. Does NOT mutate `InventoryPolicy`.

**Boundary discipline:** this is the seam where the future `0NEO/F2S_os/` will intervene (per `F2S_BOUNDARY.md §4`). Until F2S_os exists, Order2Cash_os consumes `InventoryPolicy` directly. When F2S_os is extracted, the consumer chain becomes `DemandSignalOS → F2S_os → Order2Cash_os`.

**Function interface (v0.1):** `def policies_for(sku_ids, location_ids) -> list[InventoryPolicy]` + `def pir_horizon(sku_id, location_id, horizon_days=30) -> list[PIR]`. REST endpoints v0.1.5+.

### 3.4 DemandSignalOS → Closed-loop critic v2 — forecast accuracy signal (pull, not push)

**Consumer:** the Phase-7 closed-loop critic between PlanningOS and SimOS (extended in v2 to include actuals drift as a third signal source).

**Artifact:** `ForecastAccuracy` records (per S5 + R-2):

```python
class ForecastAccuracy(BaseModel):
    schema_version: int = 1
    forecast_bundle_id: str
    sku_id: str
    location_id: str
    bucket: TimeBucket
    forecast_horizon_label: Literal["operational", "tactical", "strategic"]  # R-2
    mape: float | None                   # undefined for intermittent
    smape: float
    crps: float
    pinball_q50: float
    pinball_q90: float
    actuals_drift_flag: bool             # boolean trigger
    drift_magnitude: float | None = None # S5 — crps_degradation_ratio = current / baseline
    baseline_crps: float | None = None   # S5 — reference from walk-forward backtest
    forecast_horizon_remaining: float    # S5 — seconds remaining at scoring time
    actuals_provenance: list[str]
```

(Note per U4 + R-3: WIS is implemented in the backtesting harness as a custom metric (~50 lines, see BACKTESTING.md), NOT added to `ForecastAccuracy` schema in v0.1. CRPS + pinball loss cover similar ground. Schema inclusion deferred to v0.2.)

**Consumption pattern (pull per Round-2 architect + simos convergence):** the critic calls DemandSignalOS's accuracy function on-demand at each iteration step. DemandSignalOS does NOT push records — coupling stays one-directional (critic → DemandSignalOS).

**Function interface:**

```python
def accuracy_for_bundle(forecast_bundle_id: str, actuals_stream: Iterable[DemandActual]) -> ForecastAccuracy
def drift_since(start: datetime) -> list[ForecastAccuracy]
```

**Critic-side wiring** (in PlanningOS `closed_loop/critic/`):

- `archetypes.py` adds a new `drift_detected` detector reading `drift_magnitude` + `forecast_horizon_remaining`. Distinct from TC-driven divergence.
- Each horizon label gets its own drift threshold (strategic drift is expected; operational drift is actionable).
- The critic's `classify()` function receives `ForecastAccuracy` records alongside `TC`, `TC_SD`, `TC_DES`, `revenue`, `sla_breach_count`, `service_level` in its trajectory data.

**Migration note:** if no `forecast_horizon_label` is supplied (legacy records), the detector defaults the threshold to the operational profile (most conservative).

---

## 4. Internal contract — forecasting → inventory_policy (with `estimation/` sibling)

Per U7: `forecasting/` and `inventory_policy/` cannot have circular dependencies through lead-time estimation. Extract `estimation/` as a sibling module that BOTH can import from.

### 4.1 Module structure

```
Demand_Signal_OS/
  forecasting/          ← Nixtla wrap
  estimation/           ← NEW sibling module (U7)
    lead_time.py        ← lead-time distribution estimation
    censoring.py        ← three-tier censoring adapter
  inventory_policy/     ← custom math
```

### 4.2 Direction

**One-way: `forecasting/` produces `ForecastBundle`, `inventory_policy/` consumes via `ForecastBundle` interface only.** `inventory_policy/` modules MUST NOT import from `forecasting/<method>/` submodules.

Both `forecasting/` and `inventory_policy/` MAY import from `estimation/`. `estimation/` MAY NOT import from either.

### 4.3 Handoff artifacts

`inventory_policy/` consumes:

- `ForecastBundle` records (full quantiles, NOT collapsed to mean) from `forecasting/`
- Lead-time distributions from `estimation/lead_time.py` (derived from O2C historical lead-time observations)
- Customer-config: service-level targets (CSL or fill-rate), holding cost, stockout cost, ABC class, review cadence

`inventory_policy/` produces:

- `InventoryPolicy` records (§1.4)
- `PIR` records (§1.4)

### 4.4 Enforcement (architect Round-1 finding U7)

| Rule | Enforcement |
|---|---|
| `inventory_policy/` → `forecasting/<method>/` is FORBIDDEN | PR-review checklist + `pytest-arch`-style import-check script in CI |
| `inventory_policy/` → `estimation/` is ALLOWED | — |
| `forecasting/` → `inventory_policy/` is FORBIDDEN | PR-review + import-check |
| `estimation/` → `forecasting/` or `inventory_policy/` is FORBIDDEN | PR-review + import-check |

The only allowed import from `forecasting/` into `inventory_policy/` is the `ForecastBundle` Pydantic model — which lives in `ops_schemas/forecast.py` (nested for v0.1; promotion target `platforms_os/packages/ops_schemas/forecast.py`), NOT inside `forecasting/<method>/`.

---

## 5. Hierarchical reconciliation contract

### 5.1 Hierarchy axes

```
Product axis:   SKU → Family → Category → Total
Location axis:  Location → Region → Total
```

### 5.2 Reconciliation guarantee

For any forecast bundle served at any aggregation level:

```
sum of bottom-level forecasts at the bottom of the requested cube
  ==  forecast at the requested aggregation level
```

Applies to means and to each quantile (q05, q10, q25, q50, q75, q90, q95).

### 5.3 Methods

| Method | Status | Reference |
|---|---|---|
| **Bottom-up** | **v0.1 DEFAULT** — Nixtla `BottomUp` | Hyndman & Athanasopoulos (2021) ch. 11.2 |
| **MinT with Schäfer-Strimmer shrinkage** | **v0.2 stretch** — Nixtla `MinTrace(method='mint_shrink')` | Wickramasuriya, Athanasopoulos & Hyndman (2019), *JASA* 114(526), 804–819; Schäfer & Strimmer (2005), *Statistical Applications in Genetics and Molecular Biology* |
| Top-down | Excluded — loses bottom-level information | — |
| Middle-out | Excluded — niche | — |
| **Probabilistic reconciliation** | v0.2+ — extends to full distributions | Panagiotelis et al. (2023), *EJOR* 306(2) |

### 5.4 Reconciliation pipeline (pre-computed, materialized)

Per architect Round-1 finding: reconciliation cannot be enforced at request time for the full quantile set at 10k+ SKU scale. Implementation pattern:

1. **Forecasting pass** — each base method (ETS, Croston/TSB/SBA, GBM) produces bottom-level forecasts independently
2. **Reconciliation pass** — `BottomUp` (or MinT in v0.2) reconciles per quantile across the cube
3. **Materialization** — reconciled forecasts stored in an in-memory or on-disk cache keyed by `(sku_id, location_id, bucket, horizon_label, aggregation_level)`
4. **Serving** — bulk-query interface (or v0.1.5 REST endpoint) reads from cache; reconciliation has already happened

**Latency budget:** reconciliation pass < 5 minutes for 100k bottom series at v0.1 scale.

### 5.5 Consumer guarantee

A consumer requesting aggregated forecasts is GUARANTEED that the aggregated forecast equals the sum of the corresponding SKU-location-bucket forecasts. The reconciliation has already happened.

---

## 6. Provenance + reproducibility contract

Every consumer-visible artifact (`ForecastBundle`, `InventoryPolicy`, `PIR`, `ForecastAccuracy`) carries `ForecastProvenance` (§1.5) sufficient to:

- **Re-derive** the forecast from frozen historical data + model + seed
- **Audit** the input feature set (`feature_set_hash`)
- **Bisect** regressions (`commit_sha` of DemandSignalOS at production time)
- **Score retrospectively** (data_cut_timestamp anchors the walk-forward boundary)

An artifact lacking complete provenance is a contract violation — rejected at the function-call boundary (v0.1) or API layer (v0.1.5).

---

## 7. Versioning + evolution

### 7.1 `schema_version: int` on every artifact

Per D4. Every top-level artifact carries `schema_version: int = 1` as a non-optional field. Survives Pydantic serialization round-trip natively.

### 7.2 Breaking change policy

- **Additive changes** (new optional field, new enum value): minor version bump, backward-compatible.
- **Subtractive changes** (removed field, removed enum value): major version bump, requires consumer-side migration, requires founder approval in `DECISIONS_LOG`.
- **Semantic changes** (same field name, changed interpretation): treated as major change. PR-review rule.

### 7.3 Release-cycle policy (deferred)

Formal release-cycle definition + `Accept-Version` header for HTTP API deferred to v0.1.5 when an external consumer integrates. v0.1 library-first sequencing means consumers are in-process and pin Python package versions in `pyproject.toml` — sufficient for the v0.1 horizon.

---

## 8. `ForecastFallbackStrategy` — cold-start / NPI / promo / discontinued primitive (S6)

The single biggest gap surfaced in Round-1 brainstorming. The contract MUST exist before engine code, even if the algorithms ship in v0.1.5.

```python
class ForecastFallbackStrategy(BaseModel):
    schema_version: int = 1
    strategy_type: Literal[
        "cold_start",            # new product, no history
        "promo_uplift",          # promotional event, no historical analog
        "discontinued",          # discontinued SKU, stale history
        "insufficient_history",  # not enough data for parametric methods
        "new_location",          # new DC, no location history
    ]
    fallback: Literal[
        "family_aggregate_prior",     # borrow from family-level history
        "location_aggregate_prior",   # borrow from location-level history
        "expert_judgment_override",   # accept human-supplied forecast
        "empirical_only",             # use whatever data exists, no parametric
        "reject",                     # raise ForecastUnavailable
    ]
    config: dict  # strategy-specific configuration
```

A `ForecastBundle` may carry `fallback_applied: ForecastFallbackStrategy | None` indicating which fallback (if any) produced the bundle. `None` = standard pipeline succeeded.

**v0.1 scope:** the **contract exists**, and `forecasting/fallback.py` ships with the `reject` strategy implemented (returns 404 / raises `ForecastUnavailable`). The other strategies are implemented in v0.1.5+ when real cold-start cases hit dogfooding.

---

## 9. Internal seam enforcement summary

| Rule | Check |
|---|---|
| `forecasting/<method>/` is method-internal | external code must import via `ForecastBundle` from `ops_schemas/` |
| `inventory_policy/` is forecast-agnostic | no `from forecasting...` imports anywhere in `inventory_policy/` |
| `estimation/` is leaf module | `estimation/` may not import from `forecasting/` or `inventory_policy/` |
| `consumers/` is read-only | adapters convert types, never mutate forecasting/inventory state |
| Library-first design rules (CONSTITUTION §8) | PR-review rule + linter checks |

---

## 10. Observability (minimal v0.1)

Per architect M1 — minimal for v0.1, expanded in `OPERATIONS.md` for v0.1.5+.

| Concern | v0.1 implementation |
|---|---|
| **Structured logging** | Every forecast pipeline run emits one structured log record: `{run_id, method, sku_count, location_count, duration_ms, success_count, failure_count, fallback_count}` |
| **Trace ID propagation** | Every `ForecastBundle` carries `provenance.forecast_bundle_id` which doubles as a trace identifier. Consumers echo back. |
| **Metrics endpoint** | `def get_metrics() -> dict` library function returning per-method status, last-run timing, cache hit rates. Materialized as `GET /api/v1/metrics` in v0.1.5. |
| **Health endpoint** | `def health_check() -> dict` library function reporting per-component status (forecasting / inventory_policy / estimation / reconciliation). Materialized as `GET /api/v1/health` in v0.1.5. |

---

## 11. Failure modes (basic v0.1)

Per architect M2 — basic table for v0.1, comprehensive in `OPERATIONS.md` at v0.1.5+.

| Operation | Failure mode | Detection | Recovery action | Consumer-visible error |
|---|---|---|---|---|
| Forecast generation (per method) | Convergence failure (singular matrix, NaN, divergence) | Method wrapper catches + logs | Try fallback method per `ForecastFallbackStrategy`; if all fail → `ForecastUnavailable` | `ForecastUnavailable` exception with `strategy: "reject"` |
| Hierarchical reconciliation | MinT covariance estimation failure | Reconciliation wrapper catches | Fall back to BottomUp (v0.2 only — v0.1 already uses BottomUp) | None (silent fallback documented in provenance) |
| Policy computation | Lead-time distribution missing | Policy module raises | Fall back to last known good lead-time; if none → `PolicyUnavailable` | `PolicyUnavailable` exception |
| Ingestion | Malformed `DemandActual` record | Pydantic validation rejects | Record excluded from batch; counter incremented | Batch result reports excluded count |
| Ingestion | Feeder (O2C) unavailable during batch window | Connection retry policy | If retries exhausted → run on stale data, flag forecast provenance with `stale_inputs: true` | Provenance flag |
| Ingestion | Streaming feeder sends malformed data | Circuit breaker after N consecutive failures | Pause ingestion + alert | Health endpoint reports degraded |
| Computation | OOM at 10k SKU × walk-forward backtest | Resource monitor | Batch by SKU groups; persist intermediate results | None (transparent) |

Retry policy: exponential backoff 2× per attempt, max 5 attempts for transient failures (ingestion, I/O). Computation failures do not retry (deterministic).

---

## 12. Security (decision-documented v0.1)

Per architect M4 — explicit decision rather than implicit omission.

**v0.1 decision: NO authentication.** DemandSignalOS v0.1 is a Python library consumed in-process by SimOS / PlanningOS within a shared Docker network or local dev environment. There is no network boundary to authenticate against. Library function calls inherit the calling process's security context.

**v0.1.5 decision (when API is extracted):** authentication via the existing MAO multi-tenant tier-key system (`mao_live_*` keys). Internal Docker network endpoints get a lightweight shared secret. External-facing endpoints route through Cloudflare Tunnel + tier-key validation.

**Data classification:** demand actuals contain customer-business-sensitive information. v0.1 library writes no persistent storage. v0.1.5 storage decisions documented separately in `OPERATIONS.md`.

This is a **conscious decision** to ship v0.1 without authentication, not an omission. Documented per architect Round-1 + Round-2 guidance.

---

## 13. Resolved open questions (carried from v0)

| Q | v0 question | v0.1 resolution |
|---|---|---|
| Q1 | `CensoringFlag` realistic for O2C v0.x today? | **No — three-tier adapter required.** §2.1 |
| Q2 | `ProbabilisticDistribution` enum right for v0.1? | **Revised** to 7-family SimOS-aligned enum: `normal, lognormal, exponential, empirical, fixed, uniform, triangular`. §1.3 |
| Q3 | `ForecastAccuracy` push vs pull? | **Pull.** §3.4 |
| Q4 | Hierarchical reconciliation realistic at request time? | **No — pre-computed materialized pass.** §5.4 |
| Q5 | `InventoryPolicy.parameters` discriminated union vs dict? | **Discriminated union per `policy_type`.** §1.4 |
| Q6 | `PIR.quantiles` adds value or confuses? | **Optional (default `None`)** — ERP consumers expect deterministic; PlanningOS may use quantiles. §1.4 |
