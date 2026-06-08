# CONTRACTS — DemandSignalOS schema surface

> Contracts before engine. Every feeder and consumer relationship is specified here BEFORE any forecasting or inventory-policy code is merged.
>
> The 2026-06-08 founder rule: contracts first locks the integration before the engine has opinions.

**Status:** v0 founding draft (2026-06-08) on branch `feat/founding-design`. Pending MAO triangulation + founder approval.

**Companion documents:** `../CONSTITUTION.md`, `../F2S_BOUNDARY.md`.

---

## 0. Reading map

- §1 — Type primitives (the `ops_schemas` extension surface)
- §2 — Feeder contracts (signals INTO DemandSignalOS)
- §3 — Consumer contracts (signals OUT of DemandSignalOS)
- §4 — Internal contract: forecasting → inventory_policy
- §5 — Hierarchical reconciliation contract
- §6 — Provenance + reproducibility contract
- §7 — Versioning + evolution
- §8 — Open questions for MAO triangulation

---

## 1. Type primitives — `ops_schemas` extensions

DemandSignalOS extends the shared `ops_schemas` package with five new type families. These types are imported by SimOS, PlanningOS, and Order2Cash_os — they are the **boundary language** of the Planning2Cash loop.

### 1.1 Identity + hierarchy

```python
class SKU(BaseModel):
    sku_id: str                          # canonical SKU identifier
    family_id: str | None = None         # product family (for hierarchical reconciliation)
    category_id: str | None = None       # category (rolls up to family)
    abc_class: Literal["A", "B", "C"]    # ABC inventory classification
    archetype: ArchetypeTag              # "discrete_mfg" | "pharma" | "fashion" | ...

class Location(BaseModel):
    location_id: str
    location_type: Literal["factory", "central_dc", "regional_dc", "store", "vendor"]
    region_id: str | None = None         # region (rolls up to total)
    parent_location_id: str | None = None  # echelon-up reference

class TimeBucket(BaseModel):
    period: Literal["day", "week", "month", "quarter"]
    start: date
    end: date
    timezone: str = "UTC"
```

### 1.2 Demand signal + actual

```python
class CensoringFlag(str, Enum):
    REAL_ZERO = "real_zero"              # genuine no-demand period
    STOCKOUT_CENSORED = "stockout_censored"  # zero sales because nothing in stock
    PARTIAL_CENSORED = "partial_censored"    # some demand observed before stockout
    UNKNOWN = "unknown"                  # legacy / source did not flag

class DemandActual(BaseModel):
    """Historical actual demand observation, emitted by Order2Cash_os."""
    sku_id: str
    location_id: str
    bucket: TimeBucket
    units_sold: float                    # observed
    units_demanded: float | None = None  # if known (e.g., from order book including lost-sales)
    censoring: CensoringFlag
    stockout_duration_hours: float | None = None  # if censoring != REAL_ZERO
    source_system: str                   # provenance: "o2c" | "external_pos" | ...
    recorded_at: datetime                # when O2C recorded it

class DemandSignal(BaseModel):
    """External or transactional signal as input to forecasting."""
    sku_id: str
    location_id: str
    bucket: TimeBucket
    signal_type: Literal["actual", "pos", "promo_flag", "weather", "calendar_event", "macro"]
    value: float | str | dict            # signal-type-dependent payload
    source_system: str
    provenance_id: str                   # unique signal identifier
```

### 1.3 Forecast + distribution

```python
class Quantiles(BaseModel):
    """Probabilistic forecast as quantile estimates."""
    q05: float
    q10: float
    q25: float
    q50: float                           # median
    q75: float
    q90: float
    q95: float

class ProbabilisticDistribution(BaseModel):
    """Parametric distribution for native sampling by SimOS DES."""
    family: Literal["normal", "lognormal", "negbinom", "poisson", "tweedie", "empirical"]
    params: dict                         # family-specific parameters
    support: tuple[float, float] | None = None  # truncation bounds

class ForecastBundle(BaseModel):
    """The atomic forecast output unit."""
    sku_id: str
    location_id: str
    bucket: TimeBucket
    horizon_label: Literal["operational", "tactical", "strategic"]
    quantiles: Quantiles
    distribution: ProbabilisticDistribution | None = None  # for native sampling
    mean: float                          # convenience (= q50 for symmetric distributions)
    method: str                          # "ets" | "croston" | "tsb" | "gbm_q50" | ...
    provenance: ForecastProvenance       # see §6
```

### 1.4 Inventory policy

```python
class ReorderTrigger(BaseModel):
    trigger_type: Literal["below_reorder_point", "periodic_review", "manual"]
    sku_id: str
    location_id: str
    threshold: float | None = None       # for below_reorder_point
    review_cadence: str | None = None    # for periodic_review (e.g., "weekly_monday")

class InventoryPolicy(BaseModel):
    """Decision artifact handed to consumers."""
    sku_id: str
    location_id: str
    policy_type: Literal["newsvendor", "qr", "ss", "base_stock"]
    parameters: dict                     # (Q, R) | (s, S) | base_level | newsvendor_q
    safety_stock: float
    service_level_target: float          # alpha in (0, 1)
    reorder_triggers: list[ReorderTrigger]
    forecast_provenance: ForecastProvenance
    valid_from: datetime
    valid_until: datetime

class PIR(BaseModel):
    """Planned Independent Requirement — generalizable forecast-output artifact."""
    sku_id: str
    location_id: str
    bucket: TimeBucket
    quantity_planned: float              # planned-demand quantity for this bucket
    quantiles: Quantiles                 # uncertainty band
    forecast_provenance: ForecastProvenance
```

### 1.5 Provenance

```python
class ForecastProvenance(BaseModel):
    forecast_bundle_id: str              # unique bundle identifier
    model_id: str                        # which trained model produced this
    commit_sha: str                      # DemandSignalOS code version
    seed: int                            # RNG seed for reproducibility
    feature_set_hash: str                # hash of input feature set
    data_cut_timestamp: datetime         # frozen historical cut used for training
    produced_at: datetime                # when forecast was generated
```

---

## 2. Feeder contracts — signals INTO DemandSignalOS

Four feeder relationships. Each specifies the producer, the artifact, the cadence, and the failure mode.

### 2.1 Order2Cash_os → DemandSignalOS — transactional history with censoring

**Producer:** `Order2Cash_os` (commercial sibling, currently at `0NEO/6-Order2Cash_os/`).

**Artifact:** stream of `DemandActual` records (§1.2) with **explicit `CensoringFlag`** on every record.

**Cadence:**
- Batch nightly for historical training-set refresh
- Streaming (event-driven) for operational-horizon (near-real-time) actuals feeding closed-loop critic

**Schema requirement on O2C side:**

> Order2Cash_os MUST emit `CensoringFlag` per record. This is the **single non-negotiable upstream change** DemandSignalOS demands of O2C. Without it, the forecasts are fundamentally dishonest (zeros silently treated as no-demand when they may be stockout-censored).

**Failure mode:** if a record arrives with `CensoringFlag.UNKNOWN`, it is **excluded** from training (not silently treated as `REAL_ZERO`). Excluded record counts are tracked + reported on the forecast provenance.

**REST endpoint (on DemandSignalOS side):** `POST /api/v1/actuals/ingest` (batch) + `POST /api/v1/actuals/event` (streaming).

### 2.2 External sources → DemandSignalOS — covariate signals

**Producer:** various external systems (POS feeds, weather APIs, calendar/holiday tables, promotion calendars, event-schedule sources).

**Artifact:** stream of `DemandSignal` records (§1.2) with `signal_type ∈ {pos, promo_flag, weather, calendar_event}`.

**Cadence:** daily batch for most signals; near-real-time streaming where the source supports it.

**Failure mode:** missing covariates do not block forecasting — they degrade it. The forecasting engine MUST tolerate sparse covariate coverage and report covariate-completeness as a forecast-quality dimension.

**REST endpoint:** `POST /api/v1/signals/ingest`.

### 2.3 LitReview OS → DemandSignalOS — research-derived covariates (optional)

**Producer:** `LitReview_os/` — research-derived static features (e.g., published demand-elasticity coefficients per product category).

**Artifact:** `DemandSignal` records with `signal_type = "research_covariate"`.

**Cadence:** ad-hoc (when new research-derived features are published).

**Failure mode:** entirely optional; absence has no effect on baseline forecasting.

### 2.4 AlgoTrade OS data infra → DemandSignalOS — upstream cost-driver signals

**Producer:** `AlgoTrade_os/` data-ingestion pipelines (commodity prices, FX, macro signals).

**Artifact:** `DemandSignal` records with `signal_type = "macro"`.

**Use case:** in v0.2+, for archetypes where demand is correlated with upstream cost drivers (e.g., construction materials, raw commodities). NOT v0.1 surface.

**Cadence:** daily.

**Reuse vs. fork:** DemandSignalOS REUSES AlgoTrade's data-pipeline infrastructure (estimated ~40% transferable per `CONSTITUTION.md §3`). It does NOT fork or duplicate the data ingestion.

---

## 3. Consumer contracts — signals OUT of DemandSignalOS

Four consumer relationships. Each specifies the artifact shape, the consumption pattern, and the boundary discipline.

### 3.1 DemandSignalOS → SimOS DES — probabilistic demand distributions

**Consumer:** `simulation_os/` Discrete-Event Simulation engine.

**Artifact:** stream of `ForecastBundle` records (§1.3) with `horizon_label = "operational"` or `"tactical"`, populated `ProbabilisticDistribution`, and per-SKU-per-location-per-time-bucket granularity.

**Consumption pattern:** SimOS DES samples from `ProbabilisticDistribution` natively at simulation runtime. Point-forecast collapse is FORBIDDEN at this boundary — SimOS must receive full distribution parameters, not just `mean`.

**Inventory policy companion:** alongside forecast bundles, DemandSignalOS emits `InventoryPolicy` records (§1.4) per SKU/location. SimOS DES evaluates simulated decisions against these policies (e.g., "did the (Q,R) policy trigger reorder when it should have?").

**REST endpoint (on DemandSignalOS side):** `GET /api/v1/forecasts?horizon=operational|tactical&sku_id=...&location_id=...&bucket_start=...&bucket_end=...`.

**Failure mode:** if DemandSignalOS cannot produce a forecast for a requested (SKU, location, bucket), the response is HTTP 404 with structured error specifying the gap (missing data, insufficient history, etc.). SimOS does NOT receive a fallback forecast — fallbacks are SimOS's decision.

### 3.2 DemandSignalOS → PlanningOS SD — aggregated flow curves

**Consumer:** `Planning_os/` System Dynamics strategic-planning engine.

**Artifact:** aggregated `ForecastBundle` records with `horizon_label = "strategic"`, aggregated to (family, region, month) or coarser per PlanningOS configuration. Quantiles preserved as uncertainty bands.

**Consumption pattern:** PlanningOS SD uses aggregated forecast curves as exogenous flow inputs to its strategic flow model. The uncertainty band drives PlanningOS scenario branches.

**REST endpoint:** `GET /api/v1/forecasts?horizon=strategic&aggregation=family_region_month&...`.

**Hierarchical reconciliation:** the aggregated curves served to PlanningOS MUST be hierarchically consistent with the per-SKU forecasts served to SimOS — i.e., the sum of bottom-level forecasts equals the aggregated forecast at every aggregation level. See §5.

### 3.3 DemandSignalOS → Order2Cash_os — operational decision triggers

**Consumer:** `Order2Cash_os` (commercial sibling).

**Artifact:** `InventoryPolicy` records (§1.4) with active `ReorderTrigger` rules + near-term order-intake expectations (`PIR` records, §1.4).

**Consumption pattern:** Order2Cash_os reads policies + triggers, surfaces reorder recommendations to operations teams (or auto-executes if config allows). Order2Cash_os does NOT mutate `InventoryPolicy` — it consumes only.

**REST endpoint:** `GET /api/v1/policies?sku_id=...&location_id=...` + `GET /api/v1/pir?sku_id=...&horizon_days=30`.

**Boundary discipline:** this is the seam where the future `0NEO/F2S_os/` will intervene (per `F2S_BOUNDARY.md §4`). Until F2S_os exists, Order2Cash_os consumes `InventoryPolicy` directly. When F2S_os is extracted, the consumer chain becomes `DemandSignalOS → F2S_os → Order2Cash_os`.

### 3.4 DemandSignalOS → Closed-loop critic v2 — forecast accuracy signal

**Consumer:** the Phase-7 closed-loop critic between PlanningOS and SimOS (extended in v2 to include actuals drift as a third signal source).

**Artifact:** `ForecastAccuracy` records.

```python
class ForecastAccuracy(BaseModel):
    forecast_bundle_id: str              # which forecast we're scoring
    sku_id: str
    location_id: str
    bucket: TimeBucket
    mape: float | None                   # mean absolute percentage error
    smape: float                         # symmetric MAPE (preferred for intermittent)
    crps: float                          # continuous ranked probability score (probabilistic accuracy)
    pinball_q50: float                   # quantile loss at median
    pinball_q90: float                   # quantile loss at 90th percentile
    actuals_drift_flag: bool             # accuracy degraded beyond threshold
    actuals_provenance: list[str]        # which DemandActual records this scores
```

**Consumption pattern:** the critic reads `actuals_drift_flag` per loop iteration. If true beyond a configured fraction, the critic forces forecast recalibration before the next strategic loop. This is what makes Planning2Cash a *learning* loop, not a one-shot cascade.

**REST endpoint:** `GET /api/v1/accuracy?forecast_bundle_id=...` + `GET /api/v1/accuracy/drift?from=...&to=...`.

---

## 4. Internal contract — forecasting → inventory_policy

The internal boundary between `forecasting/` and `inventory_policy/` inside DemandSignalOS is also a contract — protected from drift.

### 4.1 Direction

**One-way: `forecasting/` produces, `inventory_policy/` consumes.** `inventory_policy/` may NOT call into `forecasting/` to trigger a forecast — it consumes already-produced `ForecastBundle` records.

### 4.2 Handoff artifact

`inventory_policy/` consumes:

- `ForecastBundle` records (full quantiles, NOT collapsed to mean)
- Lead-time distributions (separate side-input, derived from O2C historical lead-time observations)
- Customer-config: service-level targets, holding cost, stockout cost, ABC class, review cadence

`inventory_policy/` produces:

- `InventoryPolicy` records (§1.4)
- `PIR` records (§1.4)

### 4.3 The forbidden coupling

`inventory_policy/` modules MUST NOT import from specific `forecasting/<method>/` submodules. The dependency goes only through the `ForecastBundle` interface. This protects the inventory-policy math from being accidentally coupled to a forecast method's internals.

PR-review rule: any `inventory_policy/` import from `forecasting/<method>/` is rejected.

---

## 5. Hierarchical reconciliation contract

The hardest cross-cutting contract: the same demand viewed at multiple levels MUST be numerically consistent.

### 5.1 Hierarchy axes

Two axes, intersected:

**Product axis:**
```
SKU → Family → Category → Total
```

**Location axis:**
```
Location → Region → Total
```

### 5.2 Reconciliation guarantee

For any forecast bundle served at any aggregation level, the following MUST hold:

```
sum of bottom-level forecasts at the bottom of the requested cube
  ==  forecast at the requested aggregation level
```

This applies to:
- Means (point-forecast consistency)
- Each quantile (q05, q10, q25, q50, q75, q90, q95)

### 5.3 Methods

| Method | When | Reference |
|---|---|---|
| **Bottom-up** | v0.1 default, robust, no covariance estimation | Hyndman & Athanasopoulos ch. 11.2 |
| **MinT (Minimum Trace)** | v0.1 stretch, optimal under reasonable covariance | Wickramasuriya-Athanasopoulos-Hyndman 2019 |
| **Top-down** | Excluded v0.1 — loses bottom-level information | (not used) |
| **Middle-out** | Excluded v0.1 — niche | (not used) |

### 5.4 Consumer guarantee

A consumer requesting aggregated forecasts (e.g., PlanningOS requesting family-region-month) is GUARANTEED that the aggregated forecast equals the sum of the corresponding SKU-location-bucket forecasts. The reconciliation has already happened.

---

## 6. Provenance + reproducibility contract

Every consumer-visible artifact (`ForecastBundle`, `InventoryPolicy`, `PIR`, `ForecastAccuracy`) carries `ForecastProvenance` (§1.5) sufficient to:

- **Re-derive** the forecast from frozen historical data + model + seed
- **Audit** the input feature set (`feature_set_hash`)
- **Bisect** regressions (`commit_sha` of DemandSignalOS at production time)
- **Score retrospectively** (data_cut_timestamp anchors the walk-forward boundary)

A `ForecastBundle` lacking complete provenance is a contract violation and MUST be rejected at the API layer.

---

## 7. Versioning + evolution

### 7.1 Contract versioning

All artifacts carry an explicit `schema_version` field (added at the wrapper level around the typed body).

### 7.2 Breaking change policy

- **Additive changes** (new optional field, new enum value): minor version bump, backward-compatible.
- **Subtractive changes** (removed field, removed enum value, changed semantics): major version bump, requires consumer-side migration, requires founder approval recorded in `DECISIONS_LOG`.

### 7.3 Consumer onboarding

A new consumer integrates against the contract at a pinned `schema_version`. DemandSignalOS supports the previous major version for one full release cycle to allow consumer migration.

---

## 8. Open questions for MAO triangulation

1. Is `CensoringFlag` on every `DemandActual` realistic for O2C v0.x today, or does it require an O2C schema migration before DemandSignalOS v0.1 can be developed against real data? If yes — does the migration land in `0NEO/6-Order2Cash_os/` or do we adapt at ingestion?
2. Is the `ProbabilisticDistribution` enum (`normal`, `lognormal`, `negbinom`, `poisson`, `tweedie`, `empirical`) right for v0.1, or should we start with `empirical` only and add parametric families as forecasting methods justify them?
3. Should `ForecastAccuracy` records auto-stream to the critic (push), or be pulled by the critic on its own cadence? Push-vs-pull affects the closed-loop latency.
4. Is the hierarchical reconciliation guarantee (§5.2) realistic to enforce at API-response time, or does it require a pre-computed reconciliation pass and the API just serves results?
5. Should `InventoryPolicy.parameters` be a generic `dict` (current draft) or a discriminated union per `policy_type`? Discriminated union is type-safer but adds schema complexity.
6. Should `PIR` carry `quantiles` (current draft) or a `ProbabilisticDistribution` for native sampling? PIRs are typically deterministic in ERP — does carrying probabilistic information add value or just confuse downstream consumers?
