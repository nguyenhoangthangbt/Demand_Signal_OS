// PremiumGate · a clean pre-gate shown in place of a tier-gated workbench when
// the handed-off tier-key resolves BELOW Premium. Mirrors the intent of
// PlanningOS's KeyGate (planning.sim-os.ai) but matches DSO's own dark inline
// PALETTE — no cross-repo import. The actual API still enforces the tier (403 on
// Run), so this is a UX courtesy: tell the user up-front instead of letting them
// fill the whole form only to fail at submit.

// Mirror of the App.tsx PALETTE (DSO's dark theme). Kept local so this component
// is self-contained and styled consistently with the rest of the SPA.
const PALETTE = {
  bg: "#0f172a",
  bgPanel: "#1e293b",
  border: "#334155",
  text: "#f8fafc",
  textMuted: "#cbd5e1",
  textDim: "#94a3b8",
  textFaint: "#64748b",
  accent: "#fbbf24",
  accentText: "#0f172a",
  link: "#7dd3fc",
} as const;

export default function PremiumGate({ tier }: { tier?: string | null }) {
  return (
    <section style={{ padding: "2.5rem 1.5rem", maxWidth: 560, margin: "0 auto" }}>
      <div
        style={{
          padding: "2rem",
          backgroundColor: PALETTE.bgPanel,
          border: `1px solid ${PALETTE.border}`,
          borderRadius: 10,
          textAlign: "center",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "1.25rem", color: PALETTE.text }}>
          DemandSignalOS forecasting is a Premium feature
        </h2>
        <p
          style={{
            margin: "12px 0 0",
            fontSize: "0.9rem",
            color: PALETTE.textDim,
            lineHeight: 1.6,
          }}
        >
          The forecaster leaderboard is included with SimOS Premium and Enterprise.
          {tier ? (
            <>
              {" "}
              Your current plan (<strong style={{ color: PALETTE.textMuted }}>{tier}</strong>)
              doesn't include it.
            </>
          ) : (
            " Your current plan doesn't include it."
          )}
        </p>
        <a
          href="https://sim-os.ai/pricing"
          style={{
            display: "inline-block",
            marginTop: 20,
            padding: "0.55rem 1.4rem",
            backgroundColor: PALETTE.accent,
            color: PALETTE.accentText,
            border: "none",
            borderRadius: 6,
            fontWeight: 700,
            fontSize: "0.88rem",
            textDecoration: "none",
          }}
        >
          View pricing
        </a>
        <p style={{ margin: "16px 0 0", fontSize: "0.75rem", color: PALETTE.textFaint }}>
          Already upgraded? Email{" "}
          <a href="mailto:admin@sim-os.ai" style={{ color: PALETTE.link, textDecoration: "none" }}>
            admin@sim-os.ai
          </a>
          .
        </p>
      </div>
    </section>
  );
}
