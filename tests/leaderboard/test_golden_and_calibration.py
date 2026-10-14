"""Golden FACE-CRM leaderboard: honest calibration flag + the landing hero
matches the real engine output (audit findings C-09, F-21, E-07, C-10).

C-09/F-21: the golden winner (ces) beats naive on CRPS but its 90% band
caught only 50% of actuals (50% band: 25%). It was shown as an unqualified
green "Winner". The result now carries ``winner_interval_calibration`` so the
UI can flag the under-coverage next to the win.

C-10: the DSO landing hero showed LightGBM winning at a fabricated CRPS 2.143
while the real golden run ranks gbm 7th. The hero now renders
``web/src/goldenLeaderboard.json``; this test re-derives every number in that
file from the engine, so the hero cannot drift from (or invent) a result.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from demand_signal_os.api.leaderboard_routes import (
    LeaderboardRunRequest,
    _build_actuals,
    _build_config,
)
from demand_signal_os.leaderboard import LeaderboardResult, orchestrate
from demand_signal_os.leaderboard.orchestrator import interval_calibration

_HERO_JSON = Path(__file__).resolve().parents[2] / "web" / "src" / "goldenLeaderboard.json"

# Same 52-week series the leaderboard's "Load golden example" preset embeds
# (web/src/LeaderboardView.tsx GOLDEN_FACE_CRM).
GOLDEN_FACE_CRM = [
    1185, 1211, 1181, 1291, 1283, 1294, 1232, 1305, 1288, 1263, 1286, 1286, 1292,
    1359, 1119, 1247, 1200, 1256, 1350, 1309, 1334, 1266, 1217, 1228, 1326, 1278,
    1198, 1055, 1046, 1052, 1181, 1210, 1079, 1248, 1059, 1184, 1175, 1144, 1091,
    1129, 1357, 1061, 1158, 1032, 1148, 1217, 1412, 1471, 1317, 1640, 1752, 1854,
]


@pytest.fixture(scope="module")
def golden() -> LeaderboardResult:
    # Exactly what the UI sends for the golden preset (min_train_size =
    # max(2 x 13, 52 - 2 x 4 - 1) = 43).
    req = LeaderboardRunRequest(
        sku_id="WORKBENCH", location_id="WORKBENCH", history=GOLDEN_FACE_CRM,
        bucket_period="week", start_date=date(2026, 1, 1), horizon=4,
        season_length=13, intermittent_mode="off", forecaster_set="all",
        n_windows=2, min_train_size=43, seed=42,
    )
    return orchestrate(_build_actuals(req), _build_config(req))


def test_golden_ranking_unchanged(golden: LeaderboardResult) -> None:
    # The calibration flag is display-only: ranking + hash are as before
    # (the public numbers 134.478 / 141.383 stay reproducible).
    assert golden.content_hash == "a4b94c34958a3f1f"
    assert golden.winner_method_id == "ces"
    assert round(golden.entries[0].crps, 3) == 134.478


def test_golden_winner_is_flagged_too_narrow(golden: LeaderboardResult) -> None:
    winner = golden.entries[0]
    assert (winner.coverage_50, winner.coverage_90) == (0.25, 0.5)
    assert winner.interval_calibration == "too_narrow"
    assert golden.winner_interval_calibration == "too_narrow"


def test_hero_json_matches_real_golden_run(golden: LeaderboardResult) -> None:
    hero = json.loads(_HERO_JSON.read_text(encoding="utf-8"))
    assert hero["content_hash"] == golden.content_hash
    assert hero["winner_method_id"] == golden.winner_method_id
    assert hero["winner_interval_calibration"] == golden.winner_interval_calibration
    assert hero["test_points"] == golden.entries[0].n_windows * golden.config.horizon
    got = [
        (e.rank, e.method_id, round(e.crps, 3), e.is_benchmark,
         e.beats_all_benchmarks, e.coverage_90)
        for e in golden.entries
    ]
    want = [
        (e["rank"], e["method_id"], e["crps"], e["is_benchmark"],
         e["beats_all_benchmarks"], e["coverage_90"])
        for e in hero["entries"]
    ]
    assert want == got


@pytest.mark.parametrize(
    ("cov50", "cov90", "expected"),
    [
        (0.25, 0.50, "too_narrow"),   # the golden winner
        (0.50, 0.70, "too_narrow"),   # 90% band under 75%
        (0.30, 0.90, "too_narrow"),   # 50% band under 35%
        (0.50, 0.90, "ok"),
        (0.40, 0.80, "ok"),           # inside the 0.15 tolerance
        (0.90, 1.00, "too_wide"),
        (None, 0.90, "unknown"),
    ],
)
def test_interval_calibration_rule(cov50, cov90, expected) -> None:
    assert interval_calibration(cov50, cov90) == expected
