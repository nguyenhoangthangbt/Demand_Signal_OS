// Unit tests for src/lib/simosHandoff.ts (customer journey C-01): the SimOS
// hand-off must not export until the customer states the data frequency, and
// every failure reads as plain language.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  INITIAL_FORM,
  basisQuery,
  headline,
  plainError,
  toBasis,
  type HandoffPreview,
} from "../src/lib/simosHandoff.ts";

test("no data frequency chosen means no basis (export stays disabled)", () => {
  const r = toBasis(INITIAL_FORM);
  assert.ok("problem" in r);
  assert.match((r as { problem: string }).problem, /a day, a week or a month/);
});

test("a chosen frequency gives the engine basis; units per order applies to units only", () => {
  const orders = toBasis({ ...INITIAL_FORM, dataFrequency: "month", unitsPerOrder: "3" });
  assert.ok("basis" in orders);
  assert.equal((orders as { basis: { units_per_order: number } }).basis.units_per_order, 1);
  const units = toBasis({ ...INITIAL_FORM, dataFrequency: "month", demandUnit: "units", unitsPerOrder: "3" });
  assert.deepEqual((units as { basis: unknown }).basis, {
    data_frequency: "month",
    demand_unit: "units",
    units_per_order: 3,
    operating_hours_per_day: 24,
    operating_days_per_week: 7,
  });
});

test("out-of-range hours, days and units per order are refused in plain words", () => {
  assert.match((toBasis({ ...INITIAL_FORM, dataFrequency: "day", hoursPerDay: "25" }) as { problem: string }).problem, /at most 24/);
  assert.match((toBasis({ ...INITIAL_FORM, dataFrequency: "day", daysPerWeek: "0" }) as { problem: string }).problem, /at most 7/);
  assert.match(
    (toBasis({ ...INITIAL_FORM, dataFrequency: "day", demandUnit: "units", unitsPerOrder: "-1" }) as { problem: string }).problem,
    /above 0/,
  );
});

test("basisQuery carries every field for the leaderboard endpoints", () => {
  const q = new URLSearchParams(
    basisQuery({
      data_frequency: "week",
      demand_unit: "units",
      units_per_order: 2.5,
      operating_hours_per_day: 16,
      operating_days_per_week: 5,
    }),
  );
  assert.equal(q.get("data_frequency"), "week");
  assert.equal(q.get("units_per_order"), "2.5");
  assert.equal(q.get("operating_hours_per_day"), "16");
});

test("errors never show raw status codes", () => {
  for (const s of [401, 403, 404, 409, 422, 500, null]) {
    const m = plainError(s);
    assert.doesNotMatch(m, /HTTP|\b\d{3}\b/);
  }
});

test("headline states the conversion the customer confirms", () => {
  const p: HandoffPreview = {
    basis: {
      data_frequency: "month",
      demand_unit: "units",
      units_per_order: 1,
      operating_hours_per_day: 24,
      operating_days_per_week: 7,
    },
    hours_per_period: 730.5,
    units_per_order: 1,
    explanation: "",
    steps: [{ period: 1, forecast_median: 2075.2, starts_at_hour: 0, rate_per_hour: 2.8408, noise_std: 0.1 }],
  };
  assert.equal(headline(p), "Period 1: 2,075 units a month becomes 2.84 orders an hour in SimOS.");
});
