// Plan names and links per site (audit findings E-09 / F-22).
//
// sim-os.ai is the self-serve site: DSO is sold in the Premium plan.
// plan2cash.com is Enterprise only: no self-serve plan names, no prices, so
// every plan mention there points to the Enterprise page instead.
import type { Site } from "./site";

export type CopyPart = string | { label: string; href: string };

const SELF_SERVE_PRICING = "https://sim-os.ai/pricing";
// The literal "plan2cash.com" survives the plan2cash.com edge rewrite.
const ENTERPRISE_PAGE = "https://plan2cash.com/pricing";
const P2C_ENGINE = "https://plan2cash.sim-os.ai";

/** The footer sentence as text and links, per site. */
export function footerParts(s: Site): CopyPart[] {
  if (s === "plan2cash") {
    return [
      "DemandSignalOS is part of Plan2Cash, included in the ",
      { label: "Enterprise", href: ENTERPRISE_PAGE },
      " plan and part of the ",
      { label: "P2C", href: P2C_ENGINE },
      " closed loop. Contact: admin@sim-os.ai",
    ];
  }
  return [
    "DemandSignalOS is included in the ",
    { label: "Premium", href: SELF_SERVE_PRICING },
    " plan. For ",
    { label: "Enterprise", href: ENTERPRISE_PAGE },
    ", contact admin@sim-os.ai.",
  ];
}

/** The plan that unlocks gated DSO features on this site, and where to read about it. */
export function gatedPlan(s: Site): { plan: string; href: string; linkLabel: string } {
  return s === "plan2cash"
    ? { plan: "Enterprise", href: ENTERPRISE_PAGE, linkLabel: "About Enterprise" }
    : { plan: "Premium", href: SELF_SERVE_PRICING, linkLabel: "See plans" };
}

/** Plain text of a copy, for tests and accessibility checks. */
export function partsText(parts: CopyPart[]): string {
  return parts.map((p) => (typeof p === "string" ? p : p.label)).join("");
}
