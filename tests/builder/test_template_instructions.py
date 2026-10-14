"""Template instructions name a real upload place and carry no roadmap notes.

Customer journey audit 2026-10-12, finding F-06: demand_history said "Upload to
plan2cash.sim-os.ai/#/app", which redirects to a marketing page, and "After
v0.1.5 ..." (a version roadmap note in a customer file).
"""
from __future__ import annotations

import pytest

from demand_signal_os.builder.schemas import SCHEMA_REGISTRY

FORBIDDEN = ("sim-os.ai/#", "/api/", "v0.1", "v0.2", "—", "·")


def _instructions(spec) -> str:
    sheet = next(s for s in spec.sheets if s.name == "Instructions")
    return " ".join(f.description for f in sheet.fields)


@pytest.mark.parametrize("name", sorted(SCHEMA_REGISTRY))
def test_instructions_are_customer_ready(name: str):
    text = _instructions(SCHEMA_REGISTRY[name])
    for bad in FORBIDDEN:
        assert bad not in text, (name, bad)
    assert "Templates tab in P2C" in text
