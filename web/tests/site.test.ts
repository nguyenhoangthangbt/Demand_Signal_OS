// Unit test for src/lib/site.ts. Runs on Node's built-in test runner with type
// stripping (no extra dev dependency): `npm test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { site } from "../src/lib/site.ts";

test("plan2cash.com and its subdomains are the plan2cash site", () => {
  assert.equal(site("plan2cash.com"), "plan2cash");
  assert.equal(site("demand-signal.plan2cash.com"), "plan2cash");
  assert.equal(site("p2c.plan2cash.com"), "plan2cash");
});

test("sim-os.ai, localhost and empty host are the simos site", () => {
  assert.equal(site("sim-os.ai"), "simos");
  assert.equal(site("demand-signal.sim-os.ai"), "simos");
  assert.equal(site("localhost"), "simos");
  assert.equal(site("127.0.0.1"), "simos");
  assert.equal(site(""), "simos");
});

test("look-alike hosts are not the plan2cash site", () => {
  assert.equal(site("notplan2cash.com"), "simos");
  assert.equal(site("plan2cash.com.evil.example"), "simos");
  assert.equal(site("plan2cash.sim-os.ai"), "simos");
});

test("with no argument and no window it falls back to simos", () => {
  assert.equal(typeof (globalThis as { window?: unknown }).window, "undefined");
  assert.equal(site(), "simos");
});
