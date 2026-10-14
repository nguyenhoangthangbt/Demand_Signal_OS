// Audit D-08 (2026-10-12): on a 390 px phone the live forecast chart drew its
// axis labels at 9 units on a 720-unit canvas squeezed into ~308 px, so they
// rendered at 3.8 px (5 px tall). chartFrame draws the chart at its real pixel
// width on a phone so a label of N units renders at N px.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { chartFrame, labelAnchor, plotPadding, MIN_PHONE_LABEL_PX } from "../src/lib/chartFrame.ts";

const rendered = (frame: { w: number; font: number }, px: number) => (frame.font * px) / frame.w;

test("desktop keeps the 720 x 280 canvas and 9-unit labels", () => {
  for (const px of [null, 0, 640, 818, 1200]) {
    const f = chartFrame(px);
    assert.equal(f.w, 720);
    assert.equal(f.h, 280);
    assert.equal(f.font, 9);
    assert.equal(f.small, 8);
    assert.equal(f.phone, false);
  }
});

test("on a phone every label renders at 11 px or more", () => {
  for (const px of [240, 278, 308, 358, 500, 639]) {
    const f = chartFrame(px);
    assert.equal(f.w, Math.round(px), "canvas = rendered width, scale 1");
    assert.equal(f.phone, true);
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

// The y tick labels follow the data (C-06), so "4,000" is five characters. The
// rotated "Units" title sits at x = 10 and needs about 16 units; a tick label
// is right-aligned 6 units left of the plot and is about 0.6 em per character.
const UNITS_TITLE = 16;
const tickStart = (left: number, chars: number, font: number) => left - 6 - chars * font * 0.6;

test("tick labels clear the Units title on a phone, also for 4-digit demand", () => {
  for (const px of [308, 358, 500]) {
    const f = chartFrame(px);
    for (const chars of [1, 3, 5, 6]) {
      const p = plotPadding(f, chars);
      assert.ok(tickStart(p.left, chars, f.font) >= UNITS_TITLE, `${px} px, ${chars} chars: label starts at ${tickStart(p.left, chars, f.font)}`);
      assert.ok(p.bottom >= 40, "room for the period labels and the axis title");
    }
  }
  // The fixed 34-unit phone padding put "4,000" over the title (merge of j2-dso + j2-mobile).
  assert.ok(tickStart(34, 5, 11) < UNITS_TITLE);
});

test("desktop keeps the j2-dso padding", () => {
  for (const chars of [1, 3, 5]) {
    assert.deepEqual(plotPadding(chartFrame(null), chars), { top: 20, right: 16, bottom: 40, left: 22 + chars * 6 });
  }
});

test("the live chart takes its padding from plotPadding", () => {
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(app, /plotPadding\(frame, tickLabelChars\)/);
});
