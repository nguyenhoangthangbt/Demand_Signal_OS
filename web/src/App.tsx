// DemandSignalOS v0.1 standalone web UI.
//
// DSO is library-first per CONSTITUTION L2 — no native DSO HTTP API
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
  { flag: "OBSERVED", color: PALETTE.ok, blurb: "Plain unconstrained observation. Shelf stocked, customer arrived, unit moved." },
  { flag: "REAL_ZERO", color: PALETTE.textDim, blurb: "True zero demand. Not a missing read, not a stockout — distinct so the forecaster doesn't treat it as missing." },
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
            <WorkbenchSection token={token} />
          )}
          <ForecastPreview />
          <CensoringSection />
          <ConsumersSection />
        </>
      )}
      <Footer />
    </div>
  );
}

function Header({ token, onSignOut }: { token: string; onSignOut: () => void }) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0.75rem 1.5rem",
        borderBottom: `1px solid ${PALETTE.border}`,
        backgroundColor: PALETTE.bgPanel,
      }}
    >
      <div>
        <h1 style={{ margin: 0, fontSize: "1.1rem" }}>
          DemandSignalOS{" "}
          <span style={{ fontSize: "0.7rem", color: PALETTE.textFaint }}>v0.1 preview</span>
        </h1>
        <p style={{ margin: 0, fontSize: "0.75rem", color: PALETTE.textFaint }}>
          Censoring-honest probabilistic forecasting + drift signal
        </p>
      </div>
      <nav style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <a
          href="#leaderboard"
          style={{ color: PALETTE.link, fontSize: "0.8rem", textDecoration: "none" }}
        >
          Leaderboard
        </a>
        <a
          href="#verify"
          style={{ color: PALETTE.link, fontSize: "0.8rem", textDecoration: "none" }}
        >
          Verify
        </a>
        <a
          href="#"
          style={{ color: PALETTE.link, fontSize: "0.8rem", textDecoration: "none" }}
        >
          Workbench
        </a>
        <a
          href="https://plan2cash.sim-os.ai"
          style={{ color: PALETTE.link, fontSize: "0.8rem", textDecoration: "none" }}
        >
          ↗ Plan2Cash
        </a>
        {token && (
          <button
            onClick={onSignOut}
            style={{
              fontSize: "0.7rem",
              padding: "4px 10px",
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
  return (
    <section style={{ padding: "2.5rem 1.5rem 1.5rem", maxWidth: 900, margin: "0 auto" }}>
      <span
        style={{
          fontSize: "0.65rem",
          padding: "2px 8px",
          backgroundColor: PALETTE.warnBg,
          color: PALETTE.warn,
          border: `1px solid ${PALETTE.warnBorder}`,
          borderRadius: 3,
          letterSpacing: "0.05em",
          fontWeight: 600,
        }}
      >
        v0.1 PREVIEW — DSO is library-first; runtime is via plan2cash-api
      </span>
      <h2 style={{ marginTop: 12, fontSize: "2rem", lineHeight: 1.2 }}>
        Forecasts that admit what they don't know.
      </h2>
      <p
        style={{
          fontSize: "1.05rem",
          color: PALETTE.textMuted,
          lineHeight: 1.6,
          maxWidth: 720,
        }}
      >
        Quantile-band probabilistic forecasts with an explicit censoring
        taxonomy: every observation tagged OBSERVED, REAL_ZERO,
        STOCKOUT_CENSORED, PARTIAL_CENSORED, UNKNOWN. Censoring is never
        silently coerced to zero — that's the moat over naive averaging.
      </p>
    </section>
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
          Paste your <code style={{ color: PALETTE.textMuted }}>mao_live_*</code> tier-key
          to access the DSO templates. New here? Email{" "}
          <a href="mailto:admin@sim-os.ai" style={{ color: PALETTE.link }}>
            admin@sim-os.ai
          </a>{" "}
          for a Suite seat.
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

function WorkbenchSection({ token }: { token: string }) {
  const [templates, setTemplates] = useState<TemplateMeta[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<{
    ok: boolean;
    errors: { message?: string }[];
    warnings: { message?: string }[];
  } | null>(null);
  const [runOutput, setRunOutput] = useState<{
    ok: boolean;
    note: string;
  } | null>(null);

  useEffect(() => {
    setLoadError(null); // clear any prior error so a corrected key can retry
    fetch(`${API_BASE}/api/v1/templates`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => {
        if (!r.ok) {
          if (r.status === 401 || r.status === 403) {
            throw new Error(
              "That tier key was not accepted. Check that it is a valid, active mao_live_* key, or email admin@sim-os.ai for a Suite seat.",
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
    // v0.1: no DSO HTTP API; the "run" is the in-page synthetic
    // ForecastPreview below. Surface this honestly.
    setRunOutput({
      ok: true,
      note:
        "v0.1 run: the validated workbook would be passed to DSO's Python " +
        "library for the actual forecasting pass. The sample band + drift " +
        "gauge below illustrates the shape of the output. v0.1.5 wires a " +
        "real DSO HTTP API and replaces this stub with the live result.",
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

function ForecastPreview() {
  // A representative demand series; the real forecast band below is computed
  // live from it by the DSO engine (single-method ETS fit), not hardcoded.
  const HISTORY = [42, 48, 55, 51, 58, 67, 73, 71, 65, 60, 68, 72];
  const [FORECAST, setForecast] = useState<Band[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${DSO_API}/forecast/single`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        history: HISTORY,
        horizon: 8,
        season_length: 7,
        method_id: "ets",
        band: true,
      }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => {
        if (active)
          setForecast(
            (d.band ?? []).map((b: Band) => ({
              h: b.h,
              q05: Math.round(b.q05 * 10) / 10,
              q50: Math.round(b.q50 * 10) / 10,
              q95: Math.round(b.q95 * 10) / 10,
            })),
          );
      })
      .catch((e) => {
        if (active) setErr(String(e?.message ?? e));
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      <p style={{ margin: 0, marginBottom: 16, fontSize: "0.85rem", color: PALETTE.textDim }}>
        Solid line: q50 (median). Light band: q05 to q95 (the 90% prediction
        interval). Computed live by the engine from the series below via a
        single-method ETS fit, not a hardcoded sample. The band widens with
        horizon, so uncertainty propagates rather than hiding.
      </p>
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
          not a single-forecast output — wired to a real value in a follow-up,
          not shown here as a hardcoded number. */}
    </section>
  );
}

function CensoringSection() {
  return (
    <section
      style={{
        padding: "2rem 1.5rem",
        maxWidth: 900,
        margin: "0 auto",
        borderTop: `1px solid ${PALETTE.border}`,
      }}
    >
      <h3 style={{ fontSize: "1.1rem", marginBottom: 6 }}>Censoring taxonomy (the moat)</h3>
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
      DemandSignalOS · part of the{" "}
      <a href="https://plan2cash.sim-os.ai" style={{ color: PALETTE.link, textDecoration: "none" }}>
        Plan2Cash
      </a>{" "}
      trio · v0.1 preview · admin@sim-os.ai
    </footer>
  );
}
