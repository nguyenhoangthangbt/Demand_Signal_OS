// Axis helpers for the forecast fan chart (audit finding C-06).
//
// The chart used fixed y ticks [0, 40, 80, 120, 160]. Once the data went
// above 160 the domain grew but the ticks did not, so every label collapsed
// into one overlapping stack at the bottom left. These helpers derive "nice"
// ticks from the data's own range and format them with thousands separators.

/** The step between ticks: 1, 2, 2.5 or 5 times a power of ten. */
function niceStep(rawStep: number): number {
  const power = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const scaled = rawStep / power;
  const nice = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 2.5 ? 2.5 : scaled <= 5 ? 5 : 10;
  return nice * power;
}

/**
 * Evenly spaced, round-numbered ticks covering [min, max]. The first tick is
 * at or below `min`, the last at or above `max`, and there are roughly
 * `target` intervals between them.
 */
export function niceTicks(min: number, max: number, target = 5): number[] {
  let lo = Number.isFinite(min) ? min : 0;
  let hi = Number.isFinite(max) ? max : 1;
  if (hi < lo) [lo, hi] = [hi, lo];
  if (hi === lo) hi = lo + 1;
  const step = niceStep((hi - lo) / Math.max(1, target));
  const start = Math.floor(lo / step) * step;
  const end = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  // Integer counting avoids float drift (0.1 + 0.2) in the tick values.
  const n = Math.round((end - start) / step);
  for (let i = 0; i <= n; i++) ticks.push(Number((start + i * step).toPrecision(12)));
  return ticks;
}

/** "1,250" for 1250, "12.5k" for 12500, "1.2M" for 1,200,000. */
export function formatTick(v: number): string {
  const a = Math.abs(v);
  if (a >= 1_000_000) return `${Number((v / 1_000_000).toPrecision(3))}M`;
  if (a >= 10_000) return `${Number((v / 1000).toPrecision(3))}k`;
  return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/**
 * Which period indexes (0-based over history + forecast) get an x-axis label:
 * about `target` evenly spaced, always including the first period and the
 * first forecast period so the history/forecast boundary is readable.
 */
export function xLabelIndexes(total: number, firstForecast: number, target = 8): number[] {
  if (total <= 0) return [];
  const step = Math.max(1, Math.ceil(total / target));
  const out = new Set<number>([0]);
  for (let i = 0; i < total; i += step) out.add(i);
  if (firstForecast > 0 && firstForecast < total) {
    // Drop a neighbour that would collide with the boundary label.
    for (const i of [...out]) if (i !== firstForecast && Math.abs(i - firstForecast) < step / 2) out.delete(i);
    out.add(firstForecast);
  }
  return [...out].sort((a, b) => a - b);
}
