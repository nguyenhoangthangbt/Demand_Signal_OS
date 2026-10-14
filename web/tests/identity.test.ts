// Audit 2026-10-12, theme 2.13 (B-36, C-25, F-23): the header showed
// "Smoke enterprise | PLATFORM-ENGINEER | Enterprise". Name and plan only.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { customerPlanName, identityLabel } from "../src/lib/identity.ts";

const here = dirname(fileURLToPath(import.meta.url));

test("name and plan, never the role", () => {
  assert.equal(identityLabel({ name: "Smoke premium", role: "platform-engineer", tier: "premium" }), "Smoke premium | Premium");
  assert.equal(identityLabel({ name: "Smoke enterprise", role: "platform-engineer", tier: "enterprise" }), "Smoke enterprise | Enterprise");
  assert.equal(identityLabel({ name: null, role: "simos-agents", tier: "free" }), "Free");
  assert.equal(identityLabel({ name: "A", role: "admin", tier: "internal" }), "A");
  assert.equal(identityLabel({ name: null, role: "admin", tier: null }), null);
  assert.equal(identityLabel(null), null);
});

test("only customer plans have a name", () => {
  assert.equal(customerPlanName("PRO"), "Pro");
  assert.equal(customerPlanName("internal"), null);
  assert.equal(customerPlanName(undefined), null);
});

test("the header badge renders identityLabel and never shows the role", () => {
  const src = readFileSync(join(here, "../src/IdentityBadge.tsx"), "utf8");
  assert.match(src, /identityLabel\(/);
  assert.doesNotMatch(src, /role\.toUpperCase|\.role\b|setRole/);
});

// UAT 2026-10-14 F2: at 390 px the chip "Smoke premium | Premium" ran to
// x=444 and clipped the plan. The plan is the part that must always show; the
// name truncates with an ellipsis, and on a phone the name is dropped.
test("identityParts splits name and plan so the plan never truncates", async () => {
  const { identityParts } = await import("../src/lib/identity.ts");
  assert.deepEqual(identityParts({ name: "Smoke premium", role: "x", tier: "premium" }), { name: "Smoke premium", plan: "Premium" });
  assert.deepEqual(identityParts({ name: null, role: null, tier: "free" }), { name: null, plan: "Free" });
  assert.deepEqual(identityParts({ name: "A", role: null, tier: "internal" }), { name: "A", plan: null });
  assert.equal(identityParts({ name: " ", role: null, tier: null }), null);
  assert.equal(identityParts(null), null);
});

test("the header fits a phone: compact badge, wrapping nav, truncating name", () => {
  const badge = readFileSync(join(here, "../src/IdentityBadge.tsx"), "utf8");
  assert.match(badge, /compact/);
  assert.match(badge, /textOverflow: "ellipsis"/);
  const app = readFileSync(join(here, "../src/App.tsx"), "utf8");
  assert.match(app, /<IdentityBadge token=\{token\} compact=\{isMobile\} \/>/);
  const header = app.slice(app.indexOf("function Header("), app.indexOf("function Hero("));
  assert.match(header, /flexWrap: "wrap"[^}]*minWidth: 0/s);
});
