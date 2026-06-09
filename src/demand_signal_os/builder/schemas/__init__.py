"""Per-template excel_io WorkbookSpec adapters for DemandSignalOS.

The v0.1.x DSO surface for the Plan2Cash Template Hub (Sense tab).
Mirrors `planning_os.builder.schemas` + `simulation_os.builder.schemas`
conventions — single source of truth, dynamic web form + xlsx download
+ unified validation.

Per L9 sovereignty: the WorkbookSpec lives here in DSO; Plan2Cash imports
it as a contract artefact at startup. No engine math in Plan2Cash.

v0.1.x catalog: 1 template (demand_history).
v0.1.5: full DSO HTTP API extraction + per-method tunable workbooks.
"""
from __future__ import annotations

from excel_io import WorkbookSpec

from demand_signal_os.builder.schemas.demand_history import (
    DEMAND_HISTORY_SCHEMA,
)
from demand_signal_os.builder.schemas.demand_history_multi import (
    DEMAND_HISTORY_MULTI_SCHEMA,
)

SCHEMA_REGISTRY: dict[str, WorkbookSpec] = {
    "demand_history": DEMAND_HISTORY_SCHEMA,
    "demand_history_multi": DEMAND_HISTORY_MULTI_SCHEMA,
}


def get_schema(template_name: str) -> WorkbookSpec:
    """Return the WorkbookSpec for `template_name` or raise KeyError."""
    if template_name not in SCHEMA_REGISTRY:
        raise KeyError(
            f"no excel_io schema registered for template "
            f"{template_name!r}; known: {sorted(SCHEMA_REGISTRY)}"
        )
    return SCHEMA_REGISTRY[template_name]


__all__ = [
    "DEMAND_HISTORY_SCHEMA",
    "DEMAND_HISTORY_MULTI_SCHEMA",
    "SCHEMA_REGISTRY",
    "get_schema",
]
