"""DSO demand_history_multi excel_io WorkbookSpec — batch upload.

Per L17 round-2 fix for the Demand Planner persona blocker
(2026-06-09 triangulation): the existing ``demand_history`` workbook
pins ``sku_id`` at cell F5 — that is ONE SKU per workbook. A planner
with 8500 SKUs × 4 DCs faces 34,000 workbooks. There is no daily-driver
batch path.

This workbook replaces the single-SKU header with a tall
``sku_index`` sheet (one row per SKU+location) and a tall
``observations`` sheet keyed on ``(sku_id, location_id, period_label)``.
A practitioner with 8.5k SKUs uploads ONE workbook.

v0.1.x SCOPE (THIS COMMIT): schema + validator. The DSO router
already accepts batch submission via the Plan2Cash Template Hub
upload flow; v0.2 wires per-SKU forecast emission keyed on the
identity tuple.
"""
from __future__ import annotations

from excel_io import FieldSpec, SheetSpec, TabularColumn, TabularSheetSpec, WorkbookSpec

DEMAND_HISTORY_MULTI_SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Sheet 1 — Settings (global forecasting params; same shape per SKU in v0.1)
# ---------------------------------------------------------------------------
_SETTINGS_FIELDS: list[FieldSpec] = [
    FieldSpec(
        key="horizon_label",
        label="Forecast horizon (applies to all SKUs in batch)",
        description="operational / tactical / strategic. v0.2 lets the sku_index override per row.",
        cell="F5",
        field_type="str",
        default="operational",
        yaml_path=("forecasting", "horizon_label"),
    ),
    FieldSpec(
        key="season_length",
        label="Season length (periods)",
        description="Periods per season - 7 for daily/weekly cycle, 12 for monthly.",
        cell="F6",
        field_type="int",
        min=2, max=52,
        default=7,
        yaml_path=("forecasting", "season_length"),
    ),
    FieldSpec(
        key="baseline_crps",
        label="Baseline CRPS",
        description="Baseline CRPS for drift_magnitude denominator. Same value applied to every SKU in v0.1.",
        cell="F7",
        field_type="float",
        min=0.0001, max=1000.0,
        default=2.5,
        yaml_path=("forecasting", "baseline_crps"),
    ),
    FieldSpec(
        key="seed",
        label="RNG seed",
        description="Random seed for reproducibility; cited in every ForecastBundle provenance.",
        cell="F8",
        field_type="int",
        min=0, max=2_147_483_647,
        default=42,
        yaml_path=("forecasting", "seed"),
    ),
]


# ---------------------------------------------------------------------------
# Sheet 2 — sku_index (one row per SKU+location pair)
# ---------------------------------------------------------------------------
_SKU_INDEX_COLUMNS: list[TabularColumn] = [
    TabularColumn(
        key="sku_id",
        label="SKU identifier",
        description="Stock-keeping unit identifier.",
        column="A",
        field_type="str",
        required=True,
    ),
    TabularColumn(
        key="location_id",
        label="Location identifier",
        description="DC / region / warehouse identifier.",
        column="B",
        field_type="str",
        required=True,
    ),
    TabularColumn(
        key="family_id",
        label="Family",
        description="Product family (optional; enables hierarchical reconciliation in v0.2).",
        column="C",
        field_type="str",
        required=False,
    ),
    TabularColumn(
        key="abc_class",
        label="ABC class",
        description="A / B / C classification - drives downstream safety-stock prioritisation.",
        column="D",
        field_type="enum",
        required=False,
        enum_values=["A", "B", "C"],
    ),
    TabularColumn(
        key="lifecycle_stage",
        label="Lifecycle stage",
        description="NPI / steady / phase_out - v0.2 hooks lifecycle-aware forecasting (NPI bootstrap + phase-out tail).",
        column="E",
        field_type="enum",
        required=False,
        enum_values=["NPI", "steady", "phase_out"],
    ),
]


# ---------------------------------------------------------------------------
# Sheet 3 — observations (tall fact table)
# ---------------------------------------------------------------------------
_OBSERVATIONS_COLUMNS: list[TabularColumn] = [
    TabularColumn(
        key="sku_id",
        label="SKU identifier",
        description="Must match a row in sku_index.",
        column="A",
        field_type="str",
        required=True,
    ),
    TabularColumn(
        key="location_id",
        label="Location identifier",
        description="Must match a row in sku_index.",
        column="B",
        field_type="str",
        required=True,
    ),
    TabularColumn(
        key="period_label",
        label="Period",
        description="ISO date or YYYY-Www.",
        column="C",
        field_type="str",
        required=True,
    ),
    TabularColumn(
        key="observed_demand",
        label="Observed demand",
        description="Demand value (use 0 with REAL_ZERO for true zeros; inferred floor with STOCKOUT_CENSORED).",
        column="D",
        field_type="float",
        min=0.0,
        required=True,
    ),
    TabularColumn(
        key="censoring_flag",
        label="Censoring flag",
        description="OBSERVED / REAL_ZERO / STOCKOUT_CENSORED / PARTIAL_CENSORED / UNKNOWN.",
        column="E",
        field_type="enum",
        required=True,
        enum_values=[
            "OBSERVED",
            "REAL_ZERO",
            "STOCKOUT_CENSORED",
            "PARTIAL_CENSORED",
            "UNKNOWN",
        ],
    ),
]


DEMAND_HISTORY_MULTI_SCHEMA: WorkbookSpec = WorkbookSpec(
    schema_version=DEMAND_HISTORY_MULTI_SCHEMA_VERSION,
    workbook_name="demand_history_multi",
    sheets=[
        SheetSpec(
            name="Settings",
            fields=_SETTINGS_FIELDS,
        ),
        TabularSheetSpec(
            name="sku_index",
            columns=_SKU_INDEX_COLUMNS,
            data_start_row=2,
        ),
        TabularSheetSpec(
            name="observations",
            columns=_OBSERVATIONS_COLUMNS,
            data_start_row=2,
        ),
        SheetSpec(
            name="Instructions",
            fields=[
                FieldSpec(
                    key="instructions_note",
                    label="Notes",
                    description=(
                        "Batch upload path for multi-SKU demand history. "
                        "1. Fill Settings (applies to every SKU in this workbook). "
                        "2. Add one row per SKU+location pair on the sku_index tab. "
                        "3. Add observation rows on the observations tab; (sku_id, location_id) must match a sku_index row. "
                        "4. Upload to plan2cash.sim-os.ai/#/app for validation - every (sku_id, location_id) returns a per-SKU validation report. "
                        "5. v0.1.x validates the schema; v0.2 wires per-SKU forecast emission keyed on the identity tuple."
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
    "DEMAND_HISTORY_MULTI_SCHEMA",
    "DEMAND_HISTORY_MULTI_SCHEMA_VERSION",
]
