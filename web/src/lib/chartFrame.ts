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
  /** True when the canvas is the phone one (rendered width under 640 px). */
  phone: boolean;
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
  phone: false,
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
    phone: true,
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

/**
 * Plot padding for a chart whose y tick labels are up to `tickChars` long.
 *
 * Desktop keeps the tick-width padding tuned for its 9-unit labels (C-06). On a
 * phone the labels are 11 units and follow the data too ("4,000"), so the left
 * padding grows with them: the rotated Units title needs about 16 units, then a
 * 6-unit gap, then the label at about 0.6 em per character. Both canvases keep
 * 40 units at the bottom for the period labels and the axis title.
 */
export function plotPadding(f: ChartFrame, tickChars: number): ChartFrame["padding"] {
  if (!f.phone) return { top: 20, right: 16, bottom: 40, left: 22 + tickChars * 6 };
  const left = Math.max(f.padding.left, 22 + Math.ceil(tickChars * f.font * 0.6));
  return { ...f.padding, bottom: 40, left };
}
