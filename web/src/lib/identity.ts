// What the signed-in customer sees about their own account in the header.
//
// Audit 2026-10-12, theme 2.13 (B-36, C-25, F-23): the identity chip printed
// the raw MAO role ("PLATFORM-ENGINEER"), an internal access label. A customer
// sees their name and plan (Free, Pro, Premium or Enterprise), never a role.
// The /account/whoami shim still returns the role; it is simply not shown.

export interface WhoAmI {
  name: string | null;
  role: string | null;
  tier: string | null;
}

const PLAN_NAMES: Record<string, string> = {
  free: "Free",
  pro: "Pro",
  premium: "Premium",
  enterprise: "Enterprise",
};

/** The customer-facing plan name, or null for anything that is not a plan. */
export function customerPlanName(tier: string | null | undefined): string | null {
  return PLAN_NAMES[(tier ?? "").trim().toLowerCase()] ?? null;
}

/** "Name | Plan", "Name" or "Plan"; null when there is nothing to show. */
export function identityLabel(who: WhoAmI | null | undefined): string | null {
  if (!who) return null;
  const parts: string[] = [];
  const name = (who.name ?? "").trim();
  if (name) parts.push(name);
  const plan = customerPlanName(who.tier);
  if (plan) parts.push(plan);
  return parts.length ? parts.join(" | ") : null;
}
