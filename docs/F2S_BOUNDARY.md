# F2S_BOUNDARY — what's IN, what's OUT, why, and how to extract later

> Load-bearing scope contract between **DemandSignalOS** (this repo, internal-engine + lighthouse-feeder) and the **future `0NEO/F2S_os/`** (commercial sibling to `Order2Cash_os`, customer-engagement scope).
>
> Every PR touching the boundary requires review against this document. When in doubt, default to OUT — pull only what Planning2Cash dogfooding actually needs.

**Status:** v0 founding draft (2026-06-08) on branch `feat/founding-design`. Pending MAO triangulation + founder approval.

---

## 1. Why this boundary exists

The NEO ERP architecture treats **F2S (Forecast-to-Stock)** as the supply-side companion to **O2C (Order-to-Cash)** — same grade, same scope depth. F2S spans demand management, S&OP execution, inbound delivery, DC-to-DC rebalancing, substitution, supersession, batch, quality, lifecycle, destructions, and stock reconciliation.

If DemandSignalOS absorbed the full NEO F2S surface:

- **Scope creep into ERP customization** (which is multi-hundred-billion-dollar consulting territory for a reason — every company customizes it heavily)
- **The generalizable mathematical core gets buried** under operational integration glue
- **The engine moat disappears** — you'd be selling another bespoke ERP module instead of compounding decision math across customers

The boundary splits F2S into two layers and keeps only the first inside this repo:

| Layer | Variance across companies | Build economics | Location |
|---|---|---|---|
| **Inventory-policy math** (~15% of NEO F2S) | **Low** — Pfizer / Toyota / Walmart run the same fundamental math; differences are parameters, not structure | **Build once, sell N times.** Engine economics. | **IN — `Demand_Signal_OS/`** |
| **Operational F2S** (~85% of NEO F2S) | **High** — every company customizes heavily (regulatory regime, ERP master data, batch conventions, substitution rules, supersession chains) | **Build once, fit each time.** Engagement economics. | **OUT — future `0NEO/F2S_os/`** |

This split:

- Lines up with the locked Enterprise Tier model (`DECISIONS_LOG §E #19-a`): engine = product, operational fit = engagement
- Keeps DemandSignalOS the *generalizable* part (every customer, same math)
- Preserves customer-stickiness for the future commercial `0NEO/F2S_os/` (every customer, different fit)

---

## 2. IN — what lives in DemandSignalOS

The mathematical core of "given a probabilistic forecast, what should I stock and when should I reorder."

### 2.1 Inventory-policy math (generalizable, textbook-cited)

| Capability | NEO F2S anchor (if any) | Reference |
|---|---|---|
| Safety stock calculation: `SS = z_α · σ_LTD` from forecast quantiles | (cross-cutting) | Silver-Pyke-Peterson; Zipkin ch. 6 |
| Newsvendor (single-period, perishable) | — | Zipkin ch. 9 |
| **(Q,R) continuous review** | — | Silver-Pyke-Peterson ch. 7 |
| **(s,S) periodic review** | — | Zipkin ch. 9–10 |
| Base-stock policy (lost-sales / backorder variants) | — | Zipkin ch. 6 |
| **PIR generation** (Planned Independent Requirements time-series) | `F2S.PI.S082` Demand Management — Display PIRs (NEO subprocess reference) | NEO KB + Hyndman & Athanasopoulos |
| Lead-time-demand convolution (forecast distribution × lead-time distribution) | — | Zipkin ch. 6 |
| Stockout-censored estimation | — | Nahmias 1994; Cooper-Homem-de-Mello 2006 |
| Service-level vs. cost tradeoff curves | — | Silver-Pyke-Peterson |
| Multi-echelon safety-stock allocation (single-tier vs. allocation policy) | — | Graves & Willems 2000 |

### 2.2 Hierarchical reconciliation

| Capability | Reference |
|---|---|
| Bottom-up reconciliation across SKU → family → total | Hyndman & Athanasopoulos ch. 11 |
| MinT (Minimum Trace) optimal combination | Wickramasuriya-Athanasopoulos-Hyndman 2019 |
| Location-axis reconciliation (location → region → total) | Hyndman & Athanasopoulos ch. 11 |
| Cross-axis (SKU × location) reconciliation | Hyndman & Athanasopoulos ch. 11 |

### 2.3 What makes these IN

Three properties qualify a capability as IN:

1. **Textbook-citable** — published OR / SC literature; same formula serves any company
2. **Forecast-coupled** — the math operates on forecast distributions, not on ERP master data
3. **Configurable, not customizable** — customer differences are YAML parameters (service level, lead time mean/var, holding cost, stockout cost, ABC class), never code

If a capability fails any of these three tests, it goes OUT.

---

## 3. OUT — what stays for future `0NEO/F2S_os/`

These NEO F2S subprocesses are explicitly OUT of DemandSignalOS scope. They belong to the operational ERP layer where customer-specific customization is the norm.

| NEO F2S anchor | What it is | Why OUT |
|---|---|---|
| **`F2S.IF.S004`** Inbound Delivery & Goods Reception | Receiving inbound shipments, posting to stock | ERP-specific receiving workflow |
| **`F2S.IF.S117`** Substitution & Supersession Chains | Replacing one SKU with another, lifecycle transitions | Customer-specific business rules |
| **`F2S.IF.S131`** PO/SO Master Data | Purchase-order / sales-order master data management | ERP master data — customer's existing system |
| **`F2S.IF.S136`** Direct Flow Creation | Vendor-direct-to-customer flows | Customer-specific logistics design |
| **`F2S.IF.S143`** Sending Entity Activities | Entity-level activities in flow | Customer-specific role/permission model |
| **`F2S.IF.S144`** DC-to-DC Planning / Stock Rebalancing | Lateral transfers between DCs | Customer-specific network topology + triggers |
| **`F2S.IF.S146`** DC Receiving Activities | DC-level receiving operations | Customer-specific WMS integration |
| **`F2S.IF.S253`** Stock Overview | Real-time stock-position views | Customer-specific reporting needs |
| **`F2S.IF.S255`** Direct Reverse Flows | Returns / reverse logistics | Customer-specific RMA workflow |
| **`F2S.MPS.S289/S290`** Filling / Sorting | Production-line operations | Customer-specific manufacturing |
| **`F2S.PI.S012`** Lifecycle Management (MM/SD Status) | Material lifecycle states | Customer-specific lifecycle states |
| **`F2S.QS.S137`** Batch Management | Lot/batch tracking | Industry/regulatory-specific |
| **`F2S.QS.S154`** Safety Data Management | MSDS / safety documentation | Regulatory-specific |
| **`F2S.QS.S204`** Product Compliance | Regulatory compliance checks | Industry-specific |
| **`F2S.QS.S319/S324`** Quality Control in Delivery / Production | QC workflows | Customer-specific QC SOPs |
| **`F2S.DI.S013`** Destructions Management | Scrap, expiry, destruction logging | Customer/regulatory-specific |
| **`F2S.DI.S367`** Stock Movement Reconciliation | Audit reconciliation | Customer-specific audit policy |

### 3.1 The "S&OP integration" edge case

NEO carries **`F2S.PI.S300`** S&OP E2E Planning (Parts 1 & 2) inside F2S. This sits ambiguously between layers:

- The **decision math** of S&OP (consensus forecast, capacity check, financial reconciliation) is generalizable → could be IN
- The **process workflow** of S&OP (meeting cadence, role/responsibility, sign-off gates) is customer-specific → OUT

**v0.1 decision: OUT.** S&OP workflow is not in DemandSignalOS v0.1 surface. The decision math that S&OP relies on (consensus across hierarchical levels, capacity vs. demand reconciliation) is provided to PlanningOS / SimOS as primitives — but the S&OP *process* is engagement work, not engine work.

Re-evaluate this edge case at v0.2 if Planning2Cash dogfooding hits a wall without it.

### 3.2 The "demand management" edge case

NEO carries **`F2S.PI.S082`** Demand Management — Display PIRs. PIR (Planned Independent Requirement) generation is generalizable forecast-output math → **IN**. The *display layer* and ERP-side PIR consumption (MRP runs, planning books, capacity smoothing) is operational ERP → **OUT**.

DemandSignalOS emits PIRs as a structured artifact. How a customer's existing MRP / ERP consumes them is OUT.

---

## 4. Boundary protocol — the handoff contract

When (and only when) operational F2S becomes necessary — either because Planning2Cash dogfooding cannot close without it OR a commercial engagement requires it — extraction follows this protocol:

### 4.1 Extraction direction

**Always: extract OUT of DemandSignalOS, INTO `0NEO/F2S_os/`.** Never absorb operational F2S into DemandSignalOS.

### 4.2 Extraction trigger criteria (all three must hold)

1. **A consumer beyond Planning2Cash needs the capability.** A real engagement, not speculation.
2. **The capability cannot be approximated by config in `inventory_policy/`.** Tested approximation must have failed.
3. **Founder approval recorded** in `DECISIONS_LOG` (sibling document under `commercialization/`).

### 4.3 What crosses the boundary

The handoff artifact is the **`InventoryPolicy` decision bundle**:

```python
class InventoryPolicy(BaseModel):
    sku_id: str
    location_id: str
    policy_type: Literal["newsvendor", "qr", "ss", "base_stock"]
    parameters: dict  # policy-specific (Q, R, s, S, base_level, etc.)
    safety_stock: float
    service_level_target: float
    reorder_triggers: list[ReorderTrigger]
    forecast_provenance: ForecastProvenance  # which forecast bundle generated this
    valid_from: datetime
    valid_until: datetime
```

`0NEO/F2S_os/` (when it exists) is responsible for:

- Consuming `InventoryPolicy` bundles
- Translating to customer-specific ERP commands (SAP IDocs, Oracle Fusion calls, MS Dynamics, NetSuite, etc.)
- Handling substitution / supersession / lifecycle state transitions
- Executing DC-to-DC rebalancing per customer-specific topology
- Operating batch / quality / lifecycle workflows
- Closing the loop with actuals (which flow back through `Order2Cash_os` → DemandSignalOS for re-forecasting)

### 4.4 The non-extraction rule

If a feature has been requested **but no extraction trigger criterion is met**, the answer is: **document the request, do not build**.

A `BACKLOG.md` file (future) tracks rejected / deferred operational F2S features so that when extraction is finally triggered, the backlog informs scope.

---

## 5. Discipline — how this boundary stays honest

The boundary erodes silently. These five rules keep it sharp:

1. **PR-review rule:** any PR touching `inventory_policy/` is reviewed against this document. If it adds customer-specific behavior, it's rejected.
2. **Citation rule:** every capability inside `inventory_policy/` must cite a textbook or paper in its docstring. Uncitable = customer-specific = OUT.
3. **Config-only customer variation:** customer differences are YAML config (service level, lead times, costs, ABC class, hierarchies). Never code branches per customer.
4. **OUT-list growth tracking:** each rejected / deferred operational request adds an entry to `BACKLOG.md` (future) with timestamp + reason. Periodic review (quarterly) decides if extraction is finally triggered.
5. **Annual boundary review:** once per year, re-examine the IN/OUT split against actual customer engagements. Move items only with founder approval recorded in `DECISIONS_LOG`.

---

## 6. Quick reference — the boundary at a glance

**ASK YOURSELF:** *Could the same code, with only YAML config changes, serve Pfizer's pharma DC AND Toyota's auto-parts DC AND Walmart's grocery DC?*

- **YES** → IN scope, lives in `Demand_Signal_OS/inventory_policy/`
- **NO** → OUT scope, reserved for `0NEO/F2S_os/`
- **MAYBE** → OUT (default to OUT when uncertain)

---

## 7. Open questions for MAO triangulation

1. Is `F2S.PI.S082` PIR generation properly classified as IN? The math is generalizable but PIR consumption is heavily ERP-specific — does emitting PIRs as an artifact (without consuming them) actually serve any downstream Planning2Cash consumer in v0.1?
2. Is multi-echelon safety-stock allocation (Graves-Willems) v0.1 scope, or v0.2? It requires network-topology config which begins to look customer-specific.
3. Should the `InventoryPolicy` handoff contract be versioned (v1, v2 evolution path) from day 1?
4. Is `BACKLOG.md` for rejected operational F2S requests in scope for the founding draft, or premature?
