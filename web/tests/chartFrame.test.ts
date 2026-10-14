// Audit D-08 (2026-10-12): on a 390 px phone the live forecast chart drew its
// axis labels at 9 units on a 720-unit canvas squeezed into ~308 px, so they
// rendered at 3.8 px (5 px tall). chartFrame draws the chart at its real pixel
// width on a phone so a label of N units renders at N px.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { chartFrame, labelAnchor, MIN_PHONE_LABEL_PX } from "../src/lib/chartFrame.ts";

const rendered = (frame: { w: number; font: number }, px: number) => (frame.font * px) / frame.w;

test("desktop keeps the 720 x 280 canvas and 9-unit labels", () => {
  for (const px of [null, 0, 640, 818, 1200]) {
    const f = chartFrame(px);
    assert.equal(f.w, 720);
    assert.equal(f.h, 280);
    assert.equal(f.font, 9);
    assert.equal(f.small, 8);
  }
});

test("on a phone every label renders at 11 px or more", () => {
  for (const px of [240, 278, 308, 358, 500, 639]) {
    const f = chartFrame(px);
    assert.equal(f.w, Math.round(px), "canvas = rendered width, scale 1");
    for (const units of [f.font, f.small, f.hover]) {
      const out = (units * px) / f.w;
      assert.ok(out >= MIN_PHONE_LABEL_PX, `${units} units at ${px} px renders ${out.toFixed(1)} px`);
    }
    assert.ok(f.h >= 180 && f.h <= 280, `height ${f.h}`);
  }
  // The old fixed canvas, for contrast: 3.8 px at 308 wide.
  assert.ok(rendered({ w: 720, font: 9 }, 308) < 4);
});

test("the boundary label flips left when it would run off the right edge", () => {
  const f = chartFrame(308);
  assert.equal(labelAnchor(100, "history → forecast", f), "start");
  assert.equal(labelAnchor(250, "history → forecast", f), "end");
  assert.equal(labelAnchor(200, "history → forecast", chartFrame(null)), "start");
});

test("the live chart takes its canvas from chartFrame, not a fixed 720 x 280", () => {
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(app, /const w = 720;/);
  assert.match(app, /chartFrame\(/);
});
