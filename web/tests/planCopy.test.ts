// E-09 / F-22: plan2cash.com is Enterprise only, so the DSO footer and the
// gated-feature messages must not name the self-serve Premium plan there,
// while sim-os.ai keeps exactly what it had.
import { test } from "node:test";
import assert from "node:assert/strict";
import { footerParts, gatedPlan, partsText } from "../src/lib/planCopy.ts";

test("sim-os.ai footer is unchanged", () => {
  assert.equal(
    partsText(footerParts("simos")),
    "DemandSignalOS is included in the Premium plan. For Enterprise, contact admin@sim-os.ai.",
  );
  const links = footerParts("simos").filter((p) => typeof p !== "string");
  assert.deepEqual(links, [
    { label: "Premium", href: "https://sim-os.ai/pricing" },
    { label: "Enterprise", href: "https://plan2cash.com/pricing" },
  ]);
});

test("plan2cash.com footer has no self-serve plan name, price or self-serve link", () => {
  const parts = footerParts("plan2cash");
  const text = partsText(parts);
  assert.doesNotMatch(text, /Premium|Pro\b|Free|\$/);
  for (const p of parts) {
    if (typeof p !== "string") assert.doesNotMatch(p.href, /sim-os\.ai\/pricing/);
  }
  assert.ok(parts.some((p) => typeof p !== "string" && p.label === "Enterprise" && p.href === "https://plan2cash.com/pricing"));
});

test("gated features name the right plan per site", () => {
  assert.equal(gatedPlan("simos").plan, "Premium");
  assert.equal(gatedPlan("simos").href, "https://sim-os.ai/pricing");
  assert.equal(gatedPlan("plan2cash").plan, "Enterprise");
  assert.equal(gatedPlan("plan2cash").href, "https://plan2cash.com/pricing");
});
