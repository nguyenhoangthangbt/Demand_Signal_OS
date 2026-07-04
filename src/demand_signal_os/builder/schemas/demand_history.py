"""DSO demand_history excel_io WorkbookSpec.

The v0.1.x DSO surface for the Plan2Cash Template Hub (Sense tab). A
practitioner downloads this template, fills in historical demand
observations period-by-period with explicit CensoringFlag annotations,
uploads to validate, and (in v0.1.5 with the HTTP API extraction)
submits to DSO for forecast + drift signal.

Three sheets:
  Slots                 — top-level config (sku_id, location_id,
                          horizon_label, baseline_crps,
                          min_quantile_spread, season_length, seed)
  History (tabular)     — period_label, observed_demand, censoring_flag
  Metadata+Instructions — read-only

Per L9 sovereignty + L14 thin-router: this spec lives in DSO; Plan2Cash
imports it as a contract artefact. No engine math in Plan2Cash.

Per DSO CONSTITUTION + CensoringFlag taxonomy: every demand observation
carries an explicit OBSERVED / REAL_ZERO / STOCKOUT_CENSORED /
PARTIAL_CENSORED / UNKNOWN tag. Censoring-honest demand estimation is a
DSO USP per ENGINES sec 4 + COMPETITIVE_POSITIONING.md row "Probabilistic
end-to-end".
"""
from __future__ import annotations

from excel_io import FieldSpec, SheetSpec, TabularColumn, TabularSheetSpec, WorkbookSpec

DEMAND_HISTORY_SCHEMA_VERSION = "1.0"

# Cell layout: editable values in column F starting row 5 (mirrors pn_01).

# ---------------------------------------------------------------------------
# Sheet 1 — Slots
# ---------------------------------------------------------------------------
_SLOTS_FIELDS: list[FieldSpec] = [
    FieldSpec(
        key="sku_id",
        label="SKU identifier",
        description="Stock-keeping unit identifier (free-text; opaque to DSO).",
        cell="F5",
        field_type="str",
        default="SKU-1",
        yaml_path=("identity", "sku_id"),
    ),
    FieldSpec(
        key="location_id",
        label="Location identifier",
        description="DC / region / warehouse identifier (free-text).",
        cell="F6",
        field_type="str",
        default="DC-1",
        yaml_path=("identity", "location_id"),
    ),
    FieldSpec(
        key="horizon_label",
        label="Forecast horizon",
        description="Which loop the forecast feeds - operational (daily), tactical (monthly), or strategic (quarterly). Drives the drift threshold (1.5 / 2.0 / 3.0 baseline CRPS).",
        cell="F7",
        field_type="str",
        default="operational",
        yaml_path=("forecasting", "horizon_label"),
    ),
    FieldSpec(
        key="season_length",
        label="Season length (periods)",
        description="Periods per season - 7 for daily / weekly cycle; 12 for monthly seasonality.",
        cell="F8",
        field_type="int",
        min=2, max=52,
        default=7,
        yaml_path=("forecasting", "season_length"),
    ),
    FieldSpec(
        key="baseline_crps",
        label="Baseline CRPS",
        description="Baseline continuous ranked probability score - drift_magnitude is current CRPS divided by this. Set from a prior calibration window; if unknown leave default.",
        cell="F9",
        field_type="float",
        min=0.0001, max=1000.0,
        default=2.5,
        yaml_path=("forecasting", "baseline_crps"),
    ),
    FieldSpec(
        key="min_quantile_spread",
        label="Min quantile spread (Phase A guard)",
        description="Floor on the quantile band width - prevents noiseless input from collapsing to a point forecast. Default 5.0 per DSO Phase A band-guard.",
        cell="F10",
        field_type="float",
        min=0.0, max=100.0,
        default=5.0,
        yaml_path=("forecasting", "min_quantile_spread"),
    ),
    FieldSpec(
        key="seed",
        label="RNG seed",
        description="Random seed for reproducibility - every ForecastBundle's provenance envelope cites this.",
        cell="F11",
        field_type="int",
        min=0, max=2_147_483_647,
        default=42,
        yaml_path=("forecasting", "seed"),
    ),
]


# ---------------------------------------------------------------------------
# Sheet 2 — History (tabular)
# ---------------------------------------------------------------------------
_HISTORY_COLUMNS: list[TabularColumn] = [
    TabularColumn(
        key="period_label",
        label="Period",
        description="Period identifier (free-text; ISO date or YYYY-Www).",
        column="A",
        field_type="str",
        required=True,
    ),
    TabularColumn(
        key="observed_demand",
        label="Observed demand",
        description="Demand value as recorded by the planner. Use 0 with REAL_ZERO if the period is a true zero; use the inferred floor with STOCKOUT_CENSORED if stockout-blocked.",
        column="B",
        field_type="float",
        min=0.0,
        required=True,
    ),
    TabularColumn(
        key="censoring_flag",
        label="Censoring flag",
        description="One of OBSERVED / REAL_ZERO / STOCKOUT_CENSORED / PARTIAL_CENSORED / UNKNOWN. Stockout-censored is NOT zero demand - DSO treats it as a lower bound.",
        column="C",
        field_type="enum",
        required=True,
        # Five-tier taxonomy per DSO estimation/censoring.py.
        enum_values=[
            "OBSERVED",
            "REAL_ZERO",
            "STOCKOUT_CENSORED",
            "PARTIAL_CENSORED",
            "UNKNOWN",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Workbook
# ---------------------------------------------------------------------------
DEMAND_HISTORY_SCHEMA: WorkbookSpec = WorkbookSpec(
    schema_version=DEMAND_HISTORY_SCHEMA_VERSION,
    workbook_name="demand_history",
    sheets=[
        SheetSpec(
            name="Slots",
            fields=_SLOTS_FIELDS,
        ),
        TabularSheetSpec(
            name="History",
            columns=_HISTORY_COLUMNS,
            data_start_row=2,
        ),
        SheetSpec(
            name="Instructions",
            fields=[
                FieldSpec(
                    key="instructions_note",
                    label="Notes",
                    description=(
                        "1. Fill Slots first (SKU + location + horizon). "
                        "2. Add historical demand rows on the History tab with a CensoringFlag per row. "
                        "3. STOCKOUT_CENSORED is NOT zero demand - DSO treats it as a lower bound for censoring-honest estimation. "
                        "4. Upload to plan2cash.sim-os.ai/#/app for validation. "
                        "5. After v0.1.5, validated history will run through DSO forecasting (ETS / Croston / TSB / SBA / GBM) and return a quantile-band forecast + drift signal."
                    ),
                    cell="B3",
                    field_type="str",
                    default="",
                ),
            ],
        ),
    ],
)


__all__ = [
    "DEMAND_HISTORY_SCHEMA",
    "DEMAND_HISTORY_SCHEMA_VERSION",
]
