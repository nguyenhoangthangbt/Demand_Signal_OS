// C-07 and C-09 regressions for the leaderboard page logic.
import { test } from "node:test";
import assert from "node:assert/strict";
import { planBacktest, minTrainSize } from "../src/lib/backtestPlan.ts";
import { winnerVerdict } from "../src/lib/winnerVerdict.ts";
import { describeSettings, forecastRequestSettings, clampHorizon } from "../src/lib/forecastSettings.ts";

test("C-07: 24 monthly points, season 12, horizon 6 gets a plain message", () => {
  const plan = planBacktest(24, 12, 6, 2);
  assert.equal(plan.ok, false);
  if (plan.ok) return;
  assert.match(plan.message, /24 periods/);
  assert.match(plan.message, /at least 30/);
  assert.match(plan.message, /season length of 9 or less/);
  assert.doesNotMatch(plan.message, /ValueError|history_length|min_train_size/);
});

test("C-07: the golden preset still sends min_train_size 43", () => {
  assert.equal(minTrainSize(52, 13, 4, 2), 43);
  assert.deepEqual(planBacktest(52, 13, 4, 2), { ok: true, minTrainSize: 43 });
});

test("C-07: 24 points with season 6 still runs (as it did)", () => {
  assert.equal(planBacktest(24, 6, 6, 2).ok, true);
});

test("C-09: an under-covering winner is a caution, not a green win", () => {
  const v = winnerVerdict({
    winner_method_id: "ces",
    winner_is_benchmark: false,
    winner_interval_calibration: "too_narrow",
    crps: 134.478,
    coverage_50: 0.25,
    coverage_90: 0.5,
  });
  assert.equal(v.tone, "caution");
  assert.match(v.headline, /too narrow/);
  assert.match(v.detail, /caught 50% of actuals/);
  assert.match(v.detail, /50% band 25%/);
});

test("C-09: a calibrated winner stays green", () => {
  const v = winnerVerdict({
    winner_method_id: "ets",
    winner_is_benchmark: false,
    winner_interval_calibration: "ok",
    crps: 1.2,
    coverage_50: 0.5,
    coverage_90: 0.875,
  });
  assert.equal(v.tone, "good");
});

test("benchmark winner stays the honest red message", () => {
  assert.equal(winnerVerdict({ winner_method_id: "ses", winner_is_benchmark: true }).tone, "bad");
});

test("C-05: the quick forecast asks the engine to detect the season", () => {
  assert.deepEqual(forecastRequestSettings("auto", 12), {
    horizon: 12,
    season_length: "auto",
    method_id: "auto",
  });
  assert.equal(clampHorizon(99), 24);
  assert.equal(
    describeSettings({
      season_length: 12,
      season_source: "detected",
      season_strength: 0.99,
      method_id: "ets",
      method_source: "auto",
      note: "",
    }),
    "Used ETS (exponential smoothing) with a 12-period cycle (detected).",
  );
});
