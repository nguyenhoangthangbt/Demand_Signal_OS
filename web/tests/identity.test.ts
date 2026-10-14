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
