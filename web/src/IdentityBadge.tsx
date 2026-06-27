// IdentityBadge · a subtle inline chip in the top Engines nav that confirms
// WHICH account/key + tier is active. Backed by the same-origin DSO endpoint
// GET /api/v1/account/whoami, which forwards the caller's own mao_live_ key to
// MAO /account/profile (no admin credential — the customer presents their key).
//
// Renders NOTHING when there's no token or the identity can't be resolved
// (non-mao_live_ key / MAO error / unreachable), so it never shows a broken or
// half-empty chip. Styled to blend into the muted nav (small font, faint color).

import { useEffect, useState } from "react";

// Same DSO API base the rest of App uses: same-origin "/api/v1" in dev,
// the absolute demand-signal-api base in prod (VITE_DSO_API_BASE).
const DSO_API: string =
  (import.meta.env.VITE_DSO_API_BASE as string | undefined) ?? "/api/v1";

// Mirror of the two muted PALETTE colors used by the nav (App.tsx PALETTE).
const TEXT_FAINT = "#64748b";
const LINK = "#7dd3fc";

interface WhoAmI {
  name: string | null;
  role: string | null;
  tier: string | null;
}

function cap(s: string): string {
  return s.length ? s[0].toUpperCase() + s.slice(1).toLowerCase() : s;
}

export default function IdentityBadge({ token }: { token: string }) {
  const [who, setWho] = useState<WhoAmI | null>(null);

  useEffect(() => {
    if (!token) {
      setWho(null);
      return;
    }
    let cancelled = false;
    fetch(`${DSO_API}/account/whoami`, {
      headers: { "X-API-Key": token },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: WhoAmI) => {
        if (!cancelled) setWho(d);
      })
      .catch(() => {
        if (!cancelled) setWho(null);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Nothing to show until we have a resolved name. Fail-soft: the endpoint
  // returns all-null for an unrecognized key / MAO outage.
  if (!token || !who || !who.name) return null;

  const parts = [who.name];
  if (who.role) parts.push(who.role.toUpperCase());
  if (who.tier) parts.push(cap(who.tier));

  return (
    <span
      title="Active account · role · tier"
      style={{
        marginLeft: "auto",
        color: TEXT_FAINT,
        fontSize: "0.75rem",
        whiteSpace: "nowrap",
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        maxWidth: "100%",
        overflow: "hidden",
        textOverflow: "ellipsis",
      }}
    >
      <span style={{ color: LINK }}>●</span>
      {parts.join(" · ")}
    </span>
  );
}
