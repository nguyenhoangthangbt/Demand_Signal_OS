// DemandSignalOS v0.1 standalone web UI.
//
// DSO is library-first per CONSTITUTION L2 · no native DSO HTTP API
// in v0.1 (port 8006 reserved for v0.1.5). This SPA hits the
// Plan2Cash router (plan2cash-api.sim-os.ai) for the demand_history
// + demand_history_multi templates that the DSO builder/schemas
// package exports.
//
// Flow: paste mao_live_* tier-key → see templates → download xlsx
// → fill → upload + validate → run → see synthetic forecast band +
// drift signal.

import { useEffect, useState } from "react";
import LeaderboardView from "./LeaderboardView";
import VerifyView from "./VerifyView";

const API_BASE = "https://plan2cash-api.sim-os.ai";
// DSO's own API (leaderboard + the v0.2 single-series forecast). Same base the
// LeaderboardView uses; absolute in prod via VITE_DSO_API_BASE, "/api/v1" in dev.
const DSO_API: string = (import.meta.env.VITE_DSO_API_BASE as string | undefined) ?? "/api/v1";
const TOKEN_KEY = "dso_token_v1";

// Tiny hash-based view router (App.tsx has no React Router). The Verify trust
// gate lives at #verify; everything else renders the default workbench SPA.
function useHashView(): string {
  const [hash, setHash] = useState<string>(() => window.location.hash);
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash;
}

// useMatchMedia · subscribes to a CSS media query and re-renders on changes.
// Used to swap inline-style layouts at breakpoints (React inline styles do not
// support @media — this is the standard workaround). The mobile breakpoint is
// 768px (matches Tailwind's md: cutoff most common across the SimOS family).
function useMatchMedia(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

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
  ok: "#86efac",
  warn: "#fcd34d",
  warnBg: "#3f2f17",
  warnBorder: "#854d0e",
  error: "#fca5a5",
  errorBg: "#3f1d1d",
  errorBorder: "#7f1d1d",
  band: "#7dd3fc",
  median: "#fbbf24",
} as const;

const CENSORING_FLAGS = [
  { flag: "OBSERVED", color: PALETTE.ok, blurb: "Plain unconstrained observation. The shelf was stocked and the recorded units reflect real demand." },
  { flag: "REAL_ZERO", color: PALETTE.textDim, blurb: "True zero demand, kept distinct from a missing read so the forecaster never treats a genuine zero as a gap." },
  { flag: "STOCKOUT_CENSORED", color: PALETTE.warn, blurb: "Demand exceeded supply; recorded sales are a LOWER bound. Naive averaging here underestimates demand and starves replenishment." },
  { flag: "PARTIAL_CENSORED", color: PALETTE.warn, blurb: "Part of the period was supply-constrained. Mixed-mode; treated as a lower bound on the censored fraction." },
  { flag: "UNKNOWN", color: PALETTE.textFaint, blurb: "Missing meta. Surfaced verbatim so the planner can repair before the run, not silently coerced to OBSERVED." },
] as const;

interface TemplateMeta {
  engine: string;
  name: string;
  display_name: string;
  description: string;
  sheet_count: number;
  field_count: number;
}

export default function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [draftToken, setDraftToken] = useState<string>(token);
  // Series lifted from a validated demand_history upload -> the live forecast
  // below forecasts YOUR data, not the sample series.
  const [forecastSeries, setForecastSeries] = useState<number[] | null>(null);
  const hash = useHashView();
  const isVerify = hash === "#verify";
  const isLeaderboard = hash === "#leaderboard";

  useEffect(() => {
    if (token) localStorage.setItem(TOKEN_KEY, token);
  }, [token]);

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: PALETTE.bg,
        color: PALETTE.text,
        fontFamily:
          'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
      }}
    >
      <Header
        token={token}
        onSignOut={() => {
          localStorage.removeItem(TOKEN_KEY);
          setToken("");
          setDraftToken("");
        }}
      />
      {isVerify ? (
        <VerifyView />
      ) : isLeaderboard ? (
        <LeaderboardView />
      ) : (
        <>
          <Hero />
          {!token ? (
            <TokenGate
              draftToken={draftToken}
              setDraftToken={setDraftToken}
              onSubmit={() => setToken(draftToken.trim())}
            />
          ) : (
            <WorkbenchSection token={token} onForecastSeries={setForecastSeries} />
          )}
          <ForecastPreview series={forecastSeries} />
          <HowItWorks />
        </>
      )}
      <Footer />
    </div>
  );
}

function Header({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  const isMobile = useMatchMedia("(max-width: 640px)");
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        padding: isMobile ? "0.6rem 1rem" : "0.75rem 1.5rem",
        borderBottom: `1px solid ${PALETTE.border}`,
        backgroundColor: PALETTE.bgPanel,
      }}
    >
      <div style={{ minWidth: 0, flexShrink: 1 }}>
        <h1 style={{ margin: 0, fontSize: isMobile ? "0.95rem" : "1.1rem", whiteSpace: "nowrap" }}>
          DemandSignalOS{" "}
          <span style={{ fontSize: "0.7rem", color: PALETTE.textFaint }}>v0.1 preview</span>
        </h1>
        {/* Brand sub-line hidden on mobile to keep the header to a single row. */}
        {!isMobile && (
          <p style={{ margin: 0, fontSize: "0.75rem", color: PALETTE.textFaint }}>
            Censoring-honest probabilistic forecasting + forecaster leaderboard
          </p>
        )}
      </div>
      <nav style={{ display: "flex", gap: isMobile ? 8 : 12, alignItems: "center", flexShrink: 0 }}>
        <a
          href="#leaderboard"
          style={{ color: PALETTE.link, fontSize: isMobile ? "0.75rem" : "0.8rem", textDecoration: "none" }}
        >
          Leaderboard
        </a>
        <a
          href="#verify"
          style={{ color: PALETTE.link, fontSize: isMobile ? "0.75rem" : "0.8rem", textDecoration: "none" }}
        >
          Verify
        </a>
        {/* Plan2Cash cross-link — full label on desktop, just the arrow + initials on mobile. */}
        <a
          href="https://plan2cash.sim-os.ai"
          style={{ color: PALETTE.link, fontSize: isMobile ? "0.75rem" : "0.8rem", textDecoration: "none" }}
        >
          {isMobile ? "↗ P2C" : "↗ Plan2Cash"}
        </a>
        {token && (
          <button
            onClick={onSignOut}
            style={{
              fontSize: isMobile ? "0.65rem" : "0.7rem",
              padding: isMobile ? "3px 8px" : "4px 10px",
              backgroundColor: "transparent",
              border: `1px solid ${PALETTE.border}`,
              borderRadius: 4,
              cursor: "pointer",
              color: PALETTE.textDim,
            }}
          >
            Sign out
          </button>
        )}
      </nav>
    </header>
  );
}

function Hero() {
  const isMobile = useMatchMedia("(max-width: 768px)");
  return (
    <section
      style={{
        position: "relative",
        padding: isMobile ? "1.75rem 1rem 1rem" : "2.5rem 1.5rem 1.5rem",
        maxWidth: 900,
        margin: "0 auto",
        overflow: "hidden",
      }}
    >
      {/* Desktop: fan chart as absolute overlay on the right (decorative).
          Mobile: fan chart renders below the headline as a static panel so
          it does not overlap the text. Old behavior was a 55%-wide absolute
          element that bled across the H1 on <640px viewports. */}
      {!isMobile && <HeroFanChart />}
      <div style={{ position: "relative", maxWidth: isMobile ? "100%" : 640 }}>
        <span
          style={{
            display: "inline-block",
            fontSize: isMobile ? "0.6rem" : "0.65rem",
            padding: "2px 8px",
            backgroundColor: PALETTE.warnBg,
            color: PALETTE.warn,
            border: `1px solid ${PALETTE.warnBorder}`,
            borderRadius: 3,
            letterSpacing: "0.05em",
            fontWeight: 600,
          }}
        >
          v0.1 PREVIEW · DSO is library-first; runtime is via plan2cash-api
        </span>
        <h2 style={{ marginTop: 12, fontSize: isMobile ? "1.55rem" : "2rem", lineHeight: 1.2 }}>
          Forecasts that admit what they don't know.
        </h2>
        <p
          style={{
            fontSize: isMobile ? "0.95rem" : "1.05rem",
            color: PALETTE.textMuted,
            lineHeight: 1.6,
            maxWidth: isMobile ? "100%" : 580,
          }}
        >
          Every forecast ships as a probability band instead of a single number,
          so you can plan against the uncertainty you actually face.
        </p>
      </div>
      {isMobile && <HeroFanChart isMobile />}
    </section>
  );
}

// HeroFanChart · a lightweight decorative quantile-band ("fan chart") motif for
// the hero. Distinct from the live ForecastPreview lower down: this draws no real
// data, runs purely on SVG + CSS (no engine call), and goes still under
// prefers-reduced-motion. The widening band echoes DSO's "uncertainty propagates
// with horizon" idea as an atmospheric accent.
function HeroFanChart({ isMobile = false }: { isMobile?: boolean }) {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const set = () => setReduced(mq.matches);
    set();
    mq.addEventListener("change", set);
    return () => mq.removeEventListener("change", set);
  }, []);

  // A smooth rising median with a fan that widens left -> right. Each band is a
  // single closed path: the upper edge forward, then the lower edge as a reversed
  // cubic back to the start, then Z. q05/q95 outer, q25/q75 inner.
  const W = 520;
  const H = 300;
  const baseY = 200;
  const median = "M 0 230 C 90 215, 150 180, 230 150 S 380 110, 520 70";
  // Inner band q25..q75 (closed): upper forward, lower reversed.
  const bandInner =
    "M 0 222 C 90 200, 150 150, 230 108 S 380 40, 520 -18 " +
    "L 520 158 C 380 180, 300 200, 230 192 S 90 230, 0 238 Z";
  // Outer band q05..q95 (closed), wider still.
  const bandOuter =
    "M 0 216 C 90 188, 150 124, 230 70 S 380 -8, 520 -70 " +
    "L 520 200 C 380 214, 300 220, 230 222 S 90 240, 0 244 Z";

  return (
    <div
      aria-hidden="true"
      style={
        isMobile
          ? {
              position: "relative",
              width: "100%",
              height: 170,
              marginTop: "1.25rem",
              pointerEvents: "none",
              opacity: 0.85,
            }
          : {
              position: "absolute",
              top: 0,
              right: 0,
              width: "min(55%, 520px)",
              height: "100%",
              pointerEvents: "none",
              opacity: 0.9,
            }
      }
    >
      {/* Atmospheric glow behind the fan. */}
      <div
        className={reduced ? "dsohero-glow dsohero-still" : "dsohero-glow"}
        style={{
          position: "absolute",
          inset: 0,
          background: `radial-gradient(circle at 70% 35%, ${PALETTE.band}33, transparent 60%)`,
          filter: "blur(36px)",
        }}
      />
      <svg
        viewBox={`0 ${baseY - 260} ${W} ${H}`}
        preserveAspectRatio="xMaxYMid slice"
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }}
      >
        <defs>
          <linearGradient id="dsohero-band" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={PALETTE.band} stopOpacity="0.04" />
            <stop offset="100%" stopColor={PALETTE.band} stopOpacity="0.30" />
          </linearGradient>
          <linearGradient id="dsohero-band-outer" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={PALETTE.band} stopOpacity="0.02" />
            <stop offset="100%" stopColor={PALETTE.band} stopOpacity="0.12" />
          </linearGradient>
        </defs>
        {/* Outer band q05..q95. */}
        <path d={bandOuter} fill="url(#dsohero-band-outer)" />
        {/* Inner band q25..q75. */}
        <path d={bandInner} fill="url(#dsohero-band)" />
        {/* Median line, with a slow draw-on animation. */}
        <path
          d={median}
          fill="none"
          stroke={PALETTE.median}
          strokeWidth={2}
          strokeOpacity={0.85}
          strokeLinecap="round"
          className={reduced ? "" : "dsohero-draw"}
        />
      </svg>
      <style>{`
        .dsohero-glow { animation: dsohero-breathe 7s ease-in-out infinite; }
        @keyframes dsohero-breathe { 0%,100% { opacity: .55; } 50% { opacity: .9; } }
        .dsohero-draw {
          stroke-dasharray: 760;
          stroke-dashoffset: 760;
          animation: dsohero-trace 3.2s cubic-bezier(.4,0,.2,1) forwards;
        }
        @keyframes dsohero-trace { to { stroke-dashoffset: 0; } }
        .dsohero-still { animation: none !important; }
      `}</style>
    </div>
  );
}

function TokenGate({
  draftToken,
  setDraftToken,
  onSubmit,
}: {
  draftToken: string;
  setDraftToken: (v: string) => void;
  onSubmit: () => void;
}) {
  return (
    <section
      style={{
        padding: "0 1.5rem 2rem",
        maxWidth: 900,
        margin: "0 auto",
      }}
    >
      <div
        style={{
          padding: "1.5rem",
          backgroundColor: PALETTE.bgPanel,
          border: `1px solid ${PALETTE.border}`,
          borderRadius: 8,
        }}
      >
        <h3 style={{ margin: 0, marginBottom: 6, fontSize: "1.05rem" }}>
          Get started
        </h3>
        <p
          style={{
            margin: "0 0 12px 0",
            fontSize: "0.85rem",
            color: PALETTE.textDim,
          }}
        >
          Paste your Premium{" "}
          <code style={{ color: PALETTE.textMuted }}>mao_live_*</code> tier-key
          to unlock the template hub (download / validate / run xlsx workbooks
          through the Plan2Cash router). The live probabilistic forecast below
          works without a key. New here? Email{" "}
          <a href="mailto:admin@sim-os.ai" style={{ color: PALETTE.link }}>
            admin@sim-os.ai
          </a>{" "}
          for access.
        </p>
        <input
          type="password"
          placeholder="mao_live_..."
          value={draftToken}
          onChange={(e) => setDraftToken(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && draftToken.trim() && onSubmit()}
          style={{
            width: "100%",
            padding: "0.5rem",
            borderRadius: 4,
            border: `1px solid ${PALETTE.border}`,
            backgroundColor: PALETTE.bg,
            color: PALETTE.text,
            fontFamily: "monospace",
            fontSize: "0.85rem",
            boxSizing: "border-box",
          }}
        />
        <button
          onClick={onSubmit}
          disabled={!draftToken.trim()}
          style={{
            marginTop: 10,
            padding: "0.5rem 1rem",
            backgroundColor: PALETTE.accent,
            color: PALETTE.accentText,
            border: "none",
            borderRadius: 4,
            cursor: draftToken.trim() ? "pointer" : "not-allowed",
            opacity: draftToken.trim() ? 1 : 0.5,
            fontWeight: 600,
          }}
        >
          Continue
        </button>
      </div>
    </section>
  );
}

function WorkbenchSection({
  token,
  onForecastSeries,
}: {
  token: string;
  onForecastSeries?: (series: number[]) => void;
}) {
  const [templates, setTemplates] = useState<TemplateMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<{
    ok: boolean;
    errors: { message?: string }[];
    warnings: { message?: string }[];
    values?: Record<string, unknown> | null;
  } | null>(null);
  const [runOutput, setRunOutput] = useState<{
    ok: boolean;
    note: string;
  } | null>(null);

  useEffect(() => {
    setLoadError(null); // clear any prior error so a corrected key can retry
    // No key yet (public visitor): show the key prompt, do not attempt a
    // load that would 401 and surface a red error on first paint.
    if (!token) {
      setTemplates(null);
      return;
    }
    fetch(`${API_BASE}/api/v1/templates`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) {
          // 403 vs 401 are distinct failures · the old code collapsed both into
          // a misleading "invalid key" message. 403 means the key IS valid but
          // below the tier the hub requires for DSO templates (Premium — the
          // per-engine gate on the Plan2Cash router); 401 means the key isn't a
          // recognized mao_live_* key at all.
          if (r.status === 403) {
            throw new Error(
              "The template hub requires a Premium tier-key. Your key is valid but isn't provisioned for Premium. The live forecast below still works without a key. Contact admin@sim-os.ai to upgrade.",
            );
          }
          if (r.status === 401) {
            throw new Error(
              "That tier key wasn't recognized. It must be an active mao_live_* key. Contact admin@sim-os.ai for access.",
            );
          }
          throw new Error(`${r.status} ${r.statusText}`);
        }
        return r.json();
      })
      .then((d) => {
        const dso = (d.engines?.demandsignal ?? []) as TemplateMeta[];
        setTemplates(dso);
        if (dso.length > 0) setSelected(dso[0].name);
      })
      .catch((e) => setLoadError((e as Error).message));
  }, [token]);

  async function handleDownload(name: string) {
    try {
      const r = await fetch(
        `${API_BASE}/api/v1/templates/demandsignal/${name}/download`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(`Download failed: ${(e as Error).message}`);
    }
  }

  async function handleUpload(file: File) {
    if (!selected) return;
    setValidating(true);
    setValidateResult(null);
    setRunOutput(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(
        `${API_BASE}/api/v1/templates/demandsignal/${selected}/validate`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        },
      );
      const d = await r.json();
      setValidateResult(d);
      // On a clean validate, lift the observed-demand series so the live
      // forecast below forecasts the user's OWN uploaded data.
      if (d.ok && d.values && onForecastSeries) {
        const series = extractDemandSeries(d.values);
        if (series.length >= 4) onForecastSeries(series);
      }
    } catch (e) {
      setValidateResult({
        ok: false,
        errors: [{ message: (e as Error).message }],
        warnings: [],
      });
    } finally {
      setValidating(false);
    }
  }

  function handleRun() {
    // The probabilistic forecast below is computed LIVE by the engine
    // (ForecastPreview -> POST /forecast/single) from a sample series.
    // Batch-forecasting the UPLOADED workbook over the DSO API is v0.1.5.
    setRunOutput({
      ok: true,
      note:
        "Validated. The probabilistic forecast below is computed live by the " +
        "engine from the series shown (POST /forecast/single). Batch-forecasting " +
        "your uploaded history over the DSO HTTP API lands in v0.1.5.",
    });
  }

  return (
    <section style={{ padding: "0 1.5rem 2rem", maxWidth: 900, margin: "0 auto" }}>
      <h3 style={{ fontSize: "1.1rem", marginBottom: 6 }}>Workbench</h3>
      <p
        style={{
          margin: "0 0 14px 0",
          fontSize: "0.85rem",
          color: PALETTE.textDim,
        }}
      >
        Pick a template, download the xlsx, fill in your demand history with
        explicit CensoringFlags, upload to validate, run.
      </p>

      {loadError && (
        <div
          style={{
            padding: "0.625rem 0.875rem",
            backgroundColor: PALETTE.errorBg,
            border: `1px solid ${PALETTE.errorBorder}`,
            borderRadius: 6,
            color: PALETTE.error,
            fontSize: "0.85rem",
            marginBottom: 12,
          }}
        >
          Could not load templates: {loadError}
        </div>
      )}

      {loadError ? null : !templates ? (
        <p style={{ color: PALETTE.textDim, fontSize: "0.85rem" }}>Loading…</p>
      ) : templates.length === 0 ? (
        <p style={{ color: PALETTE.textDim, fontSize: "0.85rem" }}>
          No DSO templates in catalog.
        </p>
      ) : (
        <>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {templates.map((t) => (
              <li
                key={t.name}
                style={{
                  padding: "0.625rem 0.875rem",
                  marginBottom: 6,
                  backgroundColor:
                    selected === t.name ? "#1e3a5f" : PALETTE.bgPanel,
                  border: `1px solid ${
                    selected === t.name ? PALETTE.link : PALETTE.border
                  }`,
                  borderRadius: 6,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                }}
                onClick={() => setSelected(t.name)}
              >
                <div>
                  <p
                    style={{
                      margin: 0,
                      fontFamily: "monospace",
                      fontWeight: 600,
                    }}
                  >
                    {t.name}
                  </p>
                  <p
                    style={{
                      margin: 0,
                      fontSize: "0.7rem",
                      color: PALETTE.textDim,
                    }}
                  >
                    {t.sheet_count} sheet{t.sheet_count === 1 ? "" : "s"} ·{" "}
                    {t.field_count} field{t.field_count === 1 ? "" : "s"}
                  </p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDownload(t.name);
                  }}
                  style={{
                    padding: "4px 10px",
                    fontSize: "0.75rem",
                    color: PALETTE.text,
                    backgroundColor: "#3b82f6",
                    border: "none",
                    borderRadius: 4,
                    cursor: "pointer",
                  }}
                >
                  ↓ Download
                </button>
              </li>
            ))}
          </ul>

          <div
            style={{
              marginTop: 16,
              padding: "1rem",
              backgroundColor: PALETTE.bgPanel,
              border: `1px solid ${PALETTE.border}`,
              borderRadius: 8,
            }}
          >
            <p
              style={{
                margin: 0,
                marginBottom: 8,
                fontSize: "0.85rem",
                color: PALETTE.textDim,
              }}
            >
              Upload your filled <strong style={{ color: PALETTE.text }}>{selected}</strong> xlsx
              to validate against the schema.
            </p>
            <input
              type="file"
              accept=".xlsx"
              disabled={!selected || validating}
              onChange={(e) => e.target.files?.[0] && handleUpload(e.target.files[0])}
              style={{
                color: PALETTE.text,
                fontSize: "0.85rem",
              }}
            />
            {validating && (
              <p
                style={{
                  margin: "8px 0 0 0",
                  fontSize: "0.8rem",
                  color: PALETTE.textDim,
                }}
              >
                Validating…
              </p>
            )}
            {validateResult && (
              <div
                style={{
                  marginTop: 10,
                  padding: "0.625rem 0.75rem",
                  backgroundColor: validateResult.ok
                    ? "#0f3f24"
                    : PALETTE.errorBg,
                  border: `1px solid ${
                    validateResult.ok ? "#14532d" : PALETTE.errorBorder
                  }`,
                  borderRadius: 6,
                  fontSize: "0.8rem",
                  color: validateResult.ok ? PALETTE.ok : PALETTE.error,
                }}
              >
                {validateResult.ok
                  ? "Validation passed ✓"
                  : `${validateResult.errors.length} error(s):`}
                {!validateResult.ok && (
                  <ul style={{ margin: "4px 0 0 0", paddingLeft: 18 }}>
                    {validateResult.errors.slice(0, 5).map((e, i) => (
                      <li key={i}>{e.message ?? JSON.stringify(e)}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {validateResult?.ok && (
              <button
                onClick={handleRun}
                style={{
                  marginTop: 10,
                  padding: "0.5rem 1rem",
                  backgroundColor: PALETTE.accent,
                  color: PALETTE.accentText,
                  border: "none",
                  borderRadius: 4,
                  cursor: "pointer",
                  fontWeight: 600,
                  fontSize: "0.85rem",
                }}
              >
                ▶ Run forecast
              </button>
            )}
            {runOutput && (
              <div
                style={{
                  marginTop: 10,
                  padding: "0.625rem 0.75rem",
                  backgroundColor: PALETTE.warnBg,
                  border: `1px solid ${PALETTE.warnBorder}`,
                  borderRadius: 6,
                  fontSize: "0.8rem",
                  color: PALETTE.warn,
                }}
              >
                {runOutput.note}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

type Band = { h: number; q05: number; q50: number; q95: number };

// Parse a comma/newline/space-separated list of numbers from the editable
// forecast textarea.
function parseSeries(text: string): number[] {
  return text
    .split(/[\s,]+/)
    .map((t) => Number(t))
    .filter((n) => Number.isFinite(n));
}

// Pull the observed-demand series out of a validated demand_history workbook's
// parsed values (a sheet-name -> rows map). Scans array sheets for a numeric
// demand column so it tolerates the exact field/sheet naming.
function extractDemandSeries(values: Record<string, unknown>): number[] {
  const keys = ["observed_demand", "demand", "units", "sales", "quantity", "value"];
  for (const v of Object.values(values)) {
    if (Array.isArray(v) && v.length) {
      const rows = v as Record<string, unknown>[];
      const key = keys.find((k) =>
        rows.some((r) => r && typeof r === "object" && typeof r[k] === "number"),
      );
      if (key) {
        return rows
          .map((r) => (r && typeof r === "object" ? r[key] : null))
          .filter((x): x is number => typeof x === "number");
      }
    }
  }
  return [];
}

function ForecastPreview({ series }: { series?: number[] | null }) {
  // A representative demand series the forecast starts from; the band is always
  // computed LIVE by the DSO engine (single-method ETS). Editable, and a
  // validated demand_history upload feeds YOUR series in (see `series` prop).
  const SAMPLE = [42, 48, 55, 51, 58, 67, 73, 71, 65, 60, 68, 72];
  const [HISTORY, setHistory] = useState<number[]>(SAMPLE);
  const [text, setText] = useState<string>(SAMPLE.join(", "));
  const [FORECAST, setForecast] = useState<Band[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [usingUpload, setUsingUpload] = useState(false);
  const [busy, setBusy] = useState(false);

  const runForecast = (hist: number[]) => {
    setErr(null);
    setBusy(true);
    setHistory(hist);
    fetch(`${DSO_API}/forecast/single`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history: hist,
        horizon: 8,
        season_length: 7,
        method_id: "ets",
        band: true,
      }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) =>
        setForecast(
          (d.band ?? []).map((b: Band) => ({
            h: b.h,
            q05: Math.round(b.q05 * 10) / 10,
            q50: Math.round(b.q50 * 10) / 10,
            q95: Math.round(b.q95 * 10) / 10,
          })),
        ),
      )
      .catch((e) => setErr(String(e?.message ?? e)))
      .finally(() => setBusy(false));
  };

  // Initial: forecast the sample series once on mount.
  useEffect(() => {
    runForecast(SAMPLE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // When a validated upload lifts a series, switch to it and forecast it live.
  useEffect(() => {
    if (series && series.length >= 4) {
      setText(series.join(", "));
      setUsingUpload(true);
      runForecast(series);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series]);

  const total = HISTORY.length + FORECAST.length;
  const maxY = Math.ceil(Math.max(160, ...HISTORY, ...FORECAST.map((f) => f.q95)) * 1.05);
  const padding = { top: 20, right: 16, bottom: 26, left: 32 };
  const w = 720;
  const h = 280;
  const innerW = w - padding.left - padding.right;
  const innerH = h - padding.top - padding.bottom;
  const xStep = innerW / (total - 1);
  const yScale = (v: number) => innerH - (v / maxY) * innerH;

  const bandPoints = FORECAST.map(
    (f, i) => `${(HISTORY.length + i) * xStep + padding.left},${yScale(f.q95) + padding.top}`,
  )
    .concat(
      FORECAST.slice()
        .reverse()
        .map(
          (f, i) =>
            `${(total - 1 - i) * xStep + padding.left},${yScale(f.q05) + padding.top}`,
        ),
    )
    .join(" ");

  const historyPath = HISTORY.map((v, i) => {
    const x = i * xStep + padding.left;
    const y = yScale(v) + padding.top;
    return (i === 0 ? "M" : "L") + x + " " + y;
  }).join(" ");

  const forecastPath = FORECAST.map((f, i) => {
    const x = (HISTORY.length + i) * xStep + padding.left;
    const y = yScale(f.q50) + padding.top;
    return (i === 0 ? "M" : "L") + x + " " + y;
  }).join(" ");

  return (
    <section style={{ padding: "0 1.5rem 1.25rem", maxWidth: 900, margin: "0 auto" }}>
      <h3 style={{ fontSize: "1.1rem", marginBottom: 6 }}>
        Probabilistic forecast{" "}
        <span style={{ fontSize: "0.7rem", color: PALETTE.ok, fontWeight: 400 }}>· live</span>
      </h3>
      <p style={{ margin: 0, marginBottom: 12, fontSize: "0.85rem", color: PALETTE.textDim }}>
        Solid line: q50 (median). Light band: q05 to q95 (the 90% prediction
        interval), computed live by the engine via a single-method ETS fit. The
        band widens with horizon, so uncertainty propagates rather than hiding.{" "}
        {usingUpload ? (
          <span style={{ color: PALETTE.ok }}>
            Forecasting your uploaded demand_history.
          </span>
        ) : (
          <span>Edit the series below or upload a demand_history to forecast your own.</span>
        )}
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", marginBottom: 14, flexWrap: "wrap" }}>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          spellCheck={false}
          aria-label="Demand history (comma or newline separated)"
          style={{
            flex: 1,
            minWidth: 280,
            fontFamily: "ui-monospace, monospace",
            fontSize: "0.78rem",
            color: PALETTE.text,
            backgroundColor: PALETTE.bgPanel,
            border: `1px solid ${PALETTE.border}`,
            borderRadius: 6,
            padding: "8px 10px",
            resize: "vertical",
          }}
        />
        <button
          onClick={() => {
            const hist = parseSeries(text);
            if (hist.length >= 4) {
              setUsingUpload(false);
              runForecast(hist);
            } else {
              setErr("Enter at least 4 numbers.");
            }
          }}
          disabled={busy}
          style={{
            padding: "8px 14px",
            fontSize: "0.8rem",
            fontWeight: 600,
            color: PALETTE.accentText,
            backgroundColor: PALETTE.accent,
            border: "none",
            borderRadius: 6,
            cursor: busy ? "wait" : "pointer",
            opacity: busy ? 0.6 : 1,
            whiteSpace: "nowrap",
          }}
        >
          {busy ? "Forecasting…" : "▶ Forecast this series"}
        </button>
      </div>
      {err && (
        <p style={{ margin: "0 0 12px 0", fontSize: "0.8rem", color: PALETTE.warn }}>
          Live forecast unavailable ({err}); showing history only.
        </p>
      )}
      <div
        style={{
          backgroundColor: PALETTE.bgPanel,
          border: `1px solid ${PALETTE.border}`,
          borderRadius: 8,
          padding: "1rem",
        }}
      >
        <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
          {[0, 40, 80, 120, 160].map((v) => (
            <g key={v}>
              <line
                x1={padding.left}
                x2={w - padding.right}
                y1={yScale(v) + padding.top}
                y2={yScale(v) + padding.top}
                stroke={PALETTE.border}
                strokeWidth={0.5}
              />
              <text
                x={padding.left - 6}
                y={yScale(v) + padding.top + 3}
                fill={PALETTE.textDim}
                fontSize={9}
                textAnchor="end"
              >
                {v}
              </text>
            </g>
          ))}
          <line
            x1={(HISTORY.length - 1) * xStep + padding.left}
            x2={(HISTORY.length - 1) * xStep + padding.left}
            y1={padding.top}
            y2={h - padding.bottom}
            stroke={PALETTE.textDim}
            strokeDasharray="3 3"
            strokeWidth={0.7}
          />
          <text
            x={(HISTORY.length - 1) * xStep + padding.left + 4}
            y={padding.top + 10}
            fill={PALETTE.textDim}
            fontSize={9}
          >
            history → forecast
          </text>
          <polygon points={bandPoints} fill={PALETTE.band} fillOpacity={0.18} />
          <path d={historyPath} fill="none" stroke={PALETTE.textMuted} strokeWidth={1.5} />
          <path
            d={forecastPath}
            fill="none"
            stroke={PALETTE.median}
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
          {HISTORY.map((v, i) => (
            <circle
              key={`h-${i}`}
              cx={i * xStep + padding.left}
              cy={yScale(v) + padding.top}
              r={3}
              fill={PALETTE.text}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
          {FORECAST.map((f, i) => (
            <circle
              key={`f-${i}`}
              cx={(HISTORY.length + i) * xStep + padding.left}
              cy={yScale(f.q50) + padding.top}
              r={3}
              fill={PALETTE.median}
              onMouseEnter={() => setHover(HISTORY.length + i)}
              onMouseLeave={() => setHover(null)}
            />
          ))}
          {hover != null && hover < HISTORY.length && (
            <text
              x={hover * xStep + padding.left}
              y={yScale(HISTORY[hover]) + padding.top - 8}
              fontSize={10}
              fill={PALETTE.text}
              textAnchor="middle"
            >
              {HISTORY[hover]}
            </text>
          )}
          {hover != null && hover >= HISTORY.length && (
            <text
              x={hover * xStep + padding.left}
              y={yScale(FORECAST[hover - HISTORY.length].q50) + padding.top - 8}
              fontSize={10}
              fill={PALETTE.median}
              textAnchor="middle"
            >
              {FORECAST[hover - HISTORY.length].q50}
              <tspan fill={PALETTE.textDim} fontSize={8}>
                {` (${FORECAST[hover - HISTORY.length].q05}–${FORECAST[hover - HISTORY.length].q95})`}
              </tspan>
            </text>
          )}
        </svg>
      </div>
      {/* Drift is a monitoring signal (current vs training accuracy over time),
          not a single-forecast output · wired to a real value in a follow-up,
          not shown here as a hardcoded number. */}
    </section>
  );
}

// Collapsible "How it works" section. Holds the censoring taxonomy detail and
// the DSO-output consumer table behind a single toggle so the landing leads with
// the value line, not the enum table. Collapsed by default.
function HowItWorks() {
  const [open, setOpen] = useState(false);
  return (
    <section
      style={{
        padding: "1.5rem 1.5rem 2rem",
        maxWidth: 900,
        margin: "0 auto",
        borderTop: `1px solid ${PALETTE.border}`,
      }}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          width: "100%",
          padding: "0.875rem 1rem",
          backgroundColor: PALETTE.bgPanel,
          border: `1px solid ${PALETTE.border}`,
          borderRadius: 8,
          cursor: "pointer",
          color: PALETTE.text,
          fontSize: "1rem",
          fontWeight: 600,
          textAlign: "left",
        }}
      >
        <span>
          How it works{" "}
          <span style={{ fontWeight: 400, fontSize: "0.85rem", color: PALETTE.textDim }}>
            · censoring taxonomy + who consumes DSO output
          </span>
        </span>
        <span
          style={{
            transition: "transform 0.2s ease",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
            color: PALETTE.textDim,
            fontSize: "0.8rem",
          }}
        >
          ▼
        </span>
      </button>
      {open && (
        <div style={{ marginTop: 12 }}>
          <CensoringSection />
          <ConsumersSection />
        </div>
      )}
    </section>
  );
}

function CensoringSection() {
  return (
    <section
      style={{
        padding: "0.5rem 0 1.5rem",
        maxWidth: 900,
        margin: "0 auto",
      }}
    >
      <h3 style={{ fontSize: "1.1rem", marginBottom: 6 }}>Censoring taxonomy</h3>
      <p
        style={{
          margin: 0,
          marginBottom: 16,
          fontSize: "0.85rem",
          color: PALETTE.textDim,
          maxWidth: 720,
        }}
      >
        Naive forecasting averages sales. Sales-as-demand is wrong when the
        shelf was empty: STOCKOUT_CENSORED days are LOWER bounds, not zeros.
        DSO breaks the loop by tagging every observation explicitly.
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {CENSORING_FLAGS.map((c) => (
          <li
            key={c.flag}
            style={{
              padding: "0.625rem 0.875rem",
              marginBottom: 6,
              backgroundColor: PALETTE.bgPanel,
              border: `1px solid ${PALETTE.border}`,
              borderRadius: 6,
              display: "grid",
              gridTemplateColumns: "150px 1fr",
              gap: "0.75rem",
              alignItems: "start",
            }}
          >
            <span
              style={{
                fontFamily: "monospace",
                color: c.color,
                fontWeight: 600,
                fontSize: "0.85rem",
              }}
            >
              {c.flag}
            </span>
            <span
              style={{ color: PALETTE.textMuted, fontSize: "0.85rem", lineHeight: 1.5 }}
            >
              {c.blurb}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ConsumersSection() {
  const rows = [
    { who: "Plan2Cash router", what: "Pulls ForecastBundle + ForecastAccuracy through the ops_schemas Forecaster Protocol; uses drift_magnitude as the closed-loop halt signal.", url: "https://plan2cash.sim-os.ai" },
    { who: "SimulationOS arrival adapter", what: "Converts ForecastBundle records into SimOS arrivals.schedule; mean clipped at 0 and noise_std capped to prevent negative draws.", url: "https://supplychain.sim-os.ai" },
    { who: "PlanningOS drift provider", what: "Phase 7+drift v2 wires DSO accuracy.evaluate() per loop iter; the critic's drift_detected archetype consumes drift_magnitude.", url: "https://planning.sim-os.ai" },
  ];
  return (
    <section
      style={{
        padding: "2rem 1.5rem",
        maxWidth: 900,
        margin: "0 auto",
        borderTop: `1px solid ${PALETTE.border}`,
      }}
    >
      <h3 style={{ fontSize: "1.1rem", marginBottom: 6 }}>Who consumes DSO output</h3>
      <p style={{ margin: 0, marginBottom: 16, fontSize: "0.85rem", color: PALETTE.textDim }}>
        DSO is library-first per CONSTITUTION L2. No public DSO HTTP API in
        v0.1; consumers import DSO as a Python package. v0.1.5 adds the HTTP
        API at port 8006.
      </p>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {rows.map((r) => (
          <li
            key={r.who}
            style={{
              padding: "0.625rem 0.875rem",
              marginBottom: 6,
              backgroundColor: PALETTE.bgPanel,
              border: `1px solid ${PALETTE.border}`,
              borderRadius: 6,
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                gap: 8,
              }}
            >
              <p style={{ margin: 0, fontWeight: 600, color: PALETTE.text }}>{r.who}</p>
              <a href={r.url} style={{ fontSize: "0.75rem", color: PALETTE.link, textDecoration: "none" }}>
                ↗ open
              </a>
            </div>
            <p style={{ margin: "4px 0 0 0", fontSize: "0.8rem", color: PALETTE.textMuted, lineHeight: 1.5 }}>
              {r.what}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Footer() {
  return (
    <footer
      style={{
        padding: "1.5rem",
        borderTop: `1px solid ${PALETTE.border}`,
        textAlign: "center",
        color: PALETTE.textFaint,
        fontSize: "0.75rem",
      }}
    >
      <div style={{ marginBottom: "0.75rem" }}>
        <span style={{ textTransform: "uppercase", letterSpacing: "0.06em", color: PALETTE.textDim, marginRight: "0.5rem" }}>
          Engines:
        </span>
        {([
          ["SimOS", "https://supplychain.sim-os.ai"],
          ["PlanningOS", "https://planning.sim-os.ai"],
          ["DemandSignalOS", "https://demand-signal.sim-os.ai"],
          ["Order2Cash", "https://o2c.sim-os.ai"],
          ["Plan2Cash", "https://plan2cash.sim-os.ai"],
          ["AI Agents", "https://agents.sim-os.ai"],
        ] as [string, string][]).map(([label, href], i) => (
          <span key={href}>
            {i > 0 ? " · " : ""}
            <a href={href} style={{ color: PALETTE.link, textDecoration: "none" }}>
              {label}
            </a>
          </span>
        ))}
      </div>
      DemandSignalOS · included in SimOS{" "}
      <a href="https://sim-os.ai/pricing" style={{ color: PALETTE.link, textDecoration: "none" }}>
        Premium
      </a>{" "}
      and{" "}
      <a href="https://sim-os.ai/enterprise/" style={{ color: PALETTE.link, textDecoration: "none" }}>
        Enterprise
      </a>{" "}
      · part of the{" "}
      <a href="https://plan2cash.sim-os.ai" style={{ color: PALETTE.link, textDecoration: "none" }}>
        Plan2Cash
      </a>{" "}
      composition · v0.1 preview · admin@sim-os.ai
    </footer>
  );
}
