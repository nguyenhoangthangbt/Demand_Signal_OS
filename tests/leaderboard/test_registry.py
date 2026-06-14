"""Registry tests — method selection + factory."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from demand_signal_os.forecasting.registry import (
    BENCHMARK_IDS,
    CONTINUOUS_FORECASTER_IDS,
    FAST_IDS,
    INTERMITTENT_IDS,
    ML_IDS,
    STATISTICAL_IDS,
    build_method,
    is_intermittent,
    select_method_ids,
)
from demand_signal_os.leaderboard.types import LeaderboardConfig

_CUT = datetime(2026, 1, 1, tzinfo=UTC)


def _cfg(**kw: object) -> LeaderboardConfig:
    base: dict[str, object] = dict(
        sku_id="SKU-1", location_id="DC-1", horizon=10, season_length=7,
        data_cut_timestamp=_CUT,
    )
    base.update(kw)
    return LeaderboardConfig(**base)  # type: ignore[arg-type]


def test_build_every_registered_method() -> None:
    cfg = _cfg()
    for method_id in (*CONTINUOUS_FORECASTER_IDS, *INTERMITTENT_IDS, *BENCHMARK_IDS):
        method = build_method(method_id, cfg)
        assert method.method_id == method_id


def test_build_unknown_method_raises() -> None:
    with pytest.raises(KeyError):
        build_method("does_not_exist", _cfg())


def test_is_intermittent_detects_sparse_series() -> None:
    dense = [10.0] * 100
    sparse = [0.0] * 40 + [5.0] * 60  # 40% zeros
    assert is_intermittent(dense) is False
    assert is_intermittent(sparse) is True
    assert is_intermittent([]) is False


def test_select_methods_off_excludes_intermittent() -> None:
    ids = select_method_ids([0.0] * 50 + [5.0] * 50, _cfg(intermittent_mode="off"))
    assert set(ids) == set(CONTINUOUS_FORECASTER_IDS) | set(BENCHMARK_IDS)


def test_select_methods_on_forces_intermittent() -> None:
    ids = select_method_ids([10.0] * 100, _cfg(intermittent_mode="on"))
    assert set(INTERMITTENT_IDS).issubset(set(ids))


def test_select_methods_auto_includes_when_sparse() -> None:
    sparse = [0.0] * 40 + [5.0] * 60
    ids = select_method_ids(sparse, _cfg(intermittent_mode="auto"))
    assert set(INTERMITTENT_IDS).issubset(set(ids))


def test_select_methods_auto_excludes_when_dense() -> None:
    ids = select_method_ids([10.0] * 100, _cfg(intermittent_mode="auto"))
    assert not set(INTERMITTENT_IDS) & set(ids)


def test_benchmarks_always_present() -> None:
    for mode in ("auto", "on", "off"):
        ids = select_method_ids([10.0] * 100, _cfg(intermittent_mode=mode))
        assert set(BENCHMARK_IDS).issubset(set(ids))


# --- forecaster_set selector -------------------------------------------------

_DENSE = [10.0 + (i % 5) for i in range(100)]


def test_set_statistical_only() -> None:
    ids = select_method_ids(_DENSE, _cfg(forecaster_set="statistical"))
    assert set(ids) == set(STATISTICAL_IDS) | set(BENCHMARK_IDS)
    assert "gbm" not in ids and not set(INTERMITTENT_IDS) & set(ids)


def test_set_ml_only() -> None:
    ids = select_method_ids(_DENSE, _cfg(forecaster_set="ml"))
    assert set(ids) == set(ML_IDS) | set(BENCHMARK_IDS)


def test_set_fast_only() -> None:
    ids = select_method_ids(_DENSE, _cfg(forecaster_set="fast"))
    assert set(ids) == set(FAST_IDS) | set(BENCHMARK_IDS)


def test_set_intermittent_class_forces_intermittent() -> None:
    # Dense series, but the class selection forces the intermittent trio.
    ids = select_method_ids(_DENSE, _cfg(forecaster_set="intermittent"))
    assert set(ids) == set(INTERMITTENT_IDS) | set(BENCHMARK_IDS)


def test_set_full_equals_all() -> None:
    sparse = [0.0] * 40 + [5.0] * 60
    a = select_method_ids(sparse, _cfg(forecaster_set="all"))
    b = select_method_ids(sparse, _cfg(forecaster_set="full"))
    assert a == b
    # full panel on a sparse series = all continuous + intermittent + benchmarks
    assert set(a) == set(CONTINUOUS_FORECASTER_IDS) | set(INTERMITTENT_IDS) | set(BENCHMARK_IDS)


def test_explicit_methods_override_set() -> None:
    ids = select_method_ids(_DENSE, _cfg(forecaster_set="ml", methods=["ets", "theta"]))
    assert set(ids) == {"ets", "theta"} | set(BENCHMARK_IDS)


def test_explicit_methods_unknown_raises() -> None:
    with pytest.raises(ValueError):
        select_method_ids(_DENSE, _cfg(methods=["ets", "prophet"]))


def test_every_set_keeps_benchmarks() -> None:
    for fs in ("all", "full", "statistical", "ml", "intermittent", "fast"):
        ids = select_method_ids(_DENSE, _cfg(forecaster_set=fs))
        assert set(BENCHMARK_IDS).issubset(set(ids)), fs
