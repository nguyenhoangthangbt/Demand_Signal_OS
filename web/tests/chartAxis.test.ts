// C-06 regression: y ticks must follow the data, not a fixed 0..160 set.
import { test } from "node:test";
import assert from "node:assert/strict";
import { niceTicks, formatTick, xLabelIndexes } from "../src/lib/chartAxis.ts";

test("ticks cover a 2,000-unit monthly series with distinct round values", () => {
  const ticks = niceTicks(0, 2199);
  assert.equal(ticks[0], 0);
  assert.ok(ticks[ticks.length - 1] >= 2199, `top tick ${ticks[ticks.length - 1]}`);
  assert.ok(ticks.length >= 4 && ticks.length <= 8, `count ${ticks.length}`);
  assert.equal(new Set(ticks).size, ticks.length);
  assert.deepEqual(ticks, [0, 500, 1000, 1500, 2000, 2500]);
});

test("ticks for the small sample series stay small", () => {
  assert.deepEqual(niceTicks(0, 77), [0, 20, 40, 60, 80]);
});

test("degenerate ranges still give at least two ticks", () => {
  assert.ok(niceTicks(5, 5).length >= 2);
  assert.ok(niceTicks(0, 0).length >= 2);
});

test("labels are readable", () => {
  assert.equal(formatTick(1500), "1,500");
  assert.equal(formatTick(25000), "25k");
  assert.equal(formatTick(1_200_000), "1.2M");
});

test("x labels include the first period and the forecast boundary", () => {
  const idx = xLabelIndexes(36, 24);
  assert.ok(idx.includes(0) && idx.includes(24));
  assert.ok(idx.length <= 10);
  assert.deepEqual(idx, [...idx].sort((a, b) => a - b));
});
