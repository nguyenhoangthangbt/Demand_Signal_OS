"""Synthetic-data generator tests."""

from __future__ import annotations

from datetime import date

import pytest

from demand_signal_os.backtest.synthetic import (
    SyntheticConfig,
    generate,
    history_values,
)
from demand_signal_os.ops_schemas import CensoringFlag


def test_generate_produces_n_buckets() -> None:
    cfg = SyntheticConfig(n_buckets=60)
    recs = generate("SKU-1", "DC-1", cfg, seed=42)
    assert len(recs) == 60


def test_generate_is_seeded() -> None:
    cfg = SyntheticConfig(n_buckets=30, noise_std=2.0)
    a = generate("SKU-1", "DC-1", cfg, seed=42)
    b = generate("SKU-1", "DC-1", cfg, seed=42)
    assert [r.units_sold for r in a] == [r.units_sold for r in b]


def test_different_seeds_diverge() -> None:
    cfg = SyntheticConfig(n_buckets=30, noise_std=2.0)
    a = generate("SKU-1", "DC-1", cfg, seed=42)
    b = generate("SKU-1", "DC-1", cfg, seed=99)
    assert [r.units_sold for r in a] != [r.units_sold for r in b]


def test_intermittency_produces_zeros() -> None:
    cfg = SyntheticConfig(n_buckets=200, intermittency_rate=0.5, noise_std=0.5)
    recs = generate("SKU-1", "DC-1", cfg, seed=42)
    zero_count = sum(1 for r in recs if r.units_sold == 0)
    # ~50% with some slack — Bernoulli with n=200 and p=0.5: 95% CI ~ [86, 114]
    assert 70 < zero_count < 130


def test_censoring_produces_stockout_flags() -> None:
    cfg = SyntheticConfig(n_buckets=200, censoring_rate=0.3, noise_std=0.5)
    recs = generate("SKU-1", "DC-1", cfg, seed=42)
    censored = [r for r in recs if r.censoring == CensoringFlag.STOCKOUT_CENSORED]
    # ~30% with slack: 95% CI ~ [50, 70]
    assert 40 <= len(censored) <= 80
    # Censored records should have stockout_duration_hours > 0
    assert all((r.stockout_duration_hours or 0) > 0 for r in censored)


def test_no_unknown_flags_after_tier1() -> None:
    """After tier-1 heuristic, every record has REAL_ZERO or STOCKOUT_CENSORED."""
    cfg = SyntheticConfig(n_buckets=60, censoring_rate=0.2)
    recs = generate("SKU-1", "DC-1", cfg, seed=42)
    assert all(r.censoring != CensoringFlag.UNKNOWN for r in recs)


def test_history_values_extracts_units_sold() -> None:
    cfg = SyntheticConfig(n_buckets=10)
    recs = generate("SKU-1", "DC-1", cfg, seed=42)
    vals = history_values(recs)
    assert vals == [r.units_sold for r in recs]
    assert len(vals) == 10


@pytest.mark.parametrize("period", ["day", "week"])
def test_supported_periods(period: str) -> None:
    cfg = SyntheticConfig(n_buckets=4, bucket_period=period, start_date=date(2026, 1, 1))
    recs = generate("SKU-1", "DC-1", cfg, seed=42)
    assert len(recs) == 4
    assert all(r.bucket.period == period for r in recs)
