// Canvas for the live forecast chart (audit D-08, 2026-10-12).
//
// The chart used a fixed 720 x 280 viewBox with 9-unit labels. On a 390 px
// phone that canvas is squeezed into about 308 px, so the axis labels
// rendered at 3.8 px. Below 640 px the canvas now takes the chart's real
// rendered width, so one unit is one pixel and an 11-unit label is 11 px.
// From 640 px up the desktop canvas is unchanged.

export const MIN_PHONE_LABEL_PX = 11;
const PHONE_MAX_PX = 640;

export interface ChartFrame {
  w: number;
  h: number;
  /** Axis and boundary label size, in canvas units. */
  font: number;
  /** Secondary label size (the q05 to q95 range on hover). */
  small: number;
  /** Hover value size. */
  hover: number;
  padding: { top: number; right: number; bottom: number; left: number };
}

const DESKTOP: ChartFrame = {
  w: 720,
  h: 280,
  font: 9,
  small: 8,
  hover: 10,
  padding: { top: 20, right: 16, bottom: 26, left: 32 },
};

/** The canvas for a chart that renders `px` CSS pixels wide (null = not measured yet). */
export function chartFrame(px: number | null | undefined): ChartFrame {
  if (!px || px >= PHONE_MAX_PX) return DESKTOP;
  const w = Math.round(px);
  return {
    w,
    h: Math.min(280, Math.max(190, Math.round(w * 0.64))),
    font: MIN_PHONE_LABEL_PX,
    small: MIN_PHONE_LABEL_PX,
    hover: 12,
    padding: { top: 22, right: 10, bottom: 22, left: 34 },
  };
}

/**
 * Anchor for a label drawn just right of x: flip it to end just left of x
 * when it would run past the right edge. Width is a rough 0.6 em per char.
 */
export function labelAnchor(x: number, text: string, f: ChartFrame): "start" | "end" {
  const width = text.length * f.font * 0.6;
  return x + 4 + width > f.w - f.padding.right ? "end" : "start";
}
