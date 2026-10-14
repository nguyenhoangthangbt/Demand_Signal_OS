// BatchForecast: forecast every SKU and location series in one uploaded file
// (audit findings C-08 and F-03).
//
// Before this, the page took one pasted series and recorded everything as
// sku_id WORKBENCH; on plan2cash.com "Run forecast" ignored a validated
// demand_history workbook. This posts the file as-is to the DSO batch route
// (POST /forecast/batch, raw body), which reads CSV, the demand_history and
// demand_history_multi templates, or any table with SKU, location, period and
// demand columns, and returns one probabilistic band per series.
//
// Gated like the leaderboard (Premium and up): the key comes from the
// sign-in (App token, else the shared mao_sso cookie).

import { useEffect, useState } from "react";
import { readSsoCookie } from "./sso";
import { authInit, isSessionToken } from "./lib/session";
import { site } from "./lib/site";
import { gatedPlan } from "./lib/planCopy";
import {
  SEASON_OPTIONS,
  DEFAULT_HORIZON,
  MAX_HORIZON,
  clampHorizon,
  parseSeasonChoice,
  type SeasonChoice,
  type ResolvedSettings,
} from "./lib/forecastSettings";

const DSO_API: string = (import.meta.env.VITE_DSO_API_BASE as string | undefined) ?? "/api/v1";

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
} as const;

interface BandStep {
  h: number;
  q05: number;
  q50: number;
  q95: number;
}

export interface BatchSeries {
  sku_id: string;
  location_id: string;
  n_points: number;
  history: number[];
  periods: string[];
  method?: string;
  settings?: ResolvedSettings;
  band?: BandStep[];
  error?: string;
  note?: string;
}

interface BatchResponse {
  source_format: string;
  n_series: number;
  n_forecast: number;
  skipped_rows: number;
  horizon: number;
  series: BatchSeries[];
}

const FORMAT_LABEL: Record<string, string> = {
  csv: "CSV file",
  xlsx: "Excel table",
  demand_history: "demand_history workbook",
  demand_history_multi: "demand_history_multi workbook",
};

function authHeaders(key: string): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/octet-stream" };
  if (key.startsWith("mao_live_")) h["Authorization"] = `Bearer ${key}`;
  else if (key) h["X-API-Key"] = key;
  return h;
}

const PLAN = gatedPlan(site());

const fmt = (v: number): string => v.toLocaleString("en-US", { maximumFractionDigits: 0 });

export default function BatchForecast({
  token,
  file: givenFile = null,
  onPickSeries,
  heading = true,
}: {
  token: string;
  /** A file handed in by the plan2cash.com template workbench (F-03). */
  file?: File | null;
  onPickSeries?: (series: number[]) => void;
  heading?: boolean;
}) {
  const [file, setFile] = useState<File | null>(givenFile);
  const [season, setSeason] = useState<SeasonChoice>("auto");
  const [horizon, setHorizon] = useState<number>(DEFAULT_HORIZON);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [result, setResult] = useState<BatchResponse | null>(null);

  // A session marker (P0-11 cookie mode) is used as is: authInit() turns it
  // into cookie credentials. Only bearer mode falls back to mao_sso.
  const key = (isSessionToken(token) ? token : token || readSsoCookie()).trim();

  async function run(target: File | null = file) {
    setError("");
    setResult(null);
    if (!target) {
      setError("Choose a CSV or Excel file first.");
      return;
    }
    if (!key) {
      setError(`Forecasting a file is part of the ${PLAN.plan} plan. Sign in with your key to use it.`);
      return;
    }
    setBusy(true);
    try {
      const qs = new URLSearchParams({
        horizon: String(clampHorizon(horizon)),
        season_length: String(season),
        method_id: "auto",
      });
      const r = await fetch(
        `${DSO_API}/forecast/batch?${qs.toString()}`,
        authInit(key, {
          method: "POST",
          headers: authHeaders(key),
          body: await target.arrayBuffer(),
        }),
      );
      if (!r.ok) {
        const detail = await r
          .json()
          .then((d: { detail?: unknown }) => (typeof d.detail === "string" ? d.detail : ""))
          .catch(() => "");
        if (r.status === 401) throw new Error("That API key was not accepted. Sign in again or check the key.");
        if (r.status === 403) {
          throw new Error(`Forecasting a file is part of the ${PLAN.plan} plan, and your key is on a different plan.`);
        }
        throw new Error(detail || "The file could not be forecast. Please try again.");
      }
      setResult((await r.json()) as BatchResponse);
    } catch (e) {
      setError(e instanceof TypeError ? "The forecast service could not be reached. Please try again." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // A file handed in by the workbench runs straight away.
  useEffect(() => {
    if (givenFile) {
      setFile(givenFile);
      void run(givenFile);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [givenFile]);

  function downloadCsv() {
    if (!result) return;
    const rows: string[][] = [["sku_id", "location_id", "step", "q05", "q50", "q95", "season_length", "method"]];
    for (const s of result.series) {
      for (const b of s.band ?? []) {
        rows.push([
          s.sku_id,
          s.location_id,
          String(b.h),
          String(b.q05),
          String(b.q50),
          String(b.q95),
          String(s.settings?.season_length ?? ""),
          s.method ?? "",
        ]);
      }
    }
    const quote = (c: string) => (/[",\n]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c);
    const csv = rows.map((r) => r.map(quote).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "dso_batch_forecast.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      {heading && (
        <>
          <h3 style={{ fontSize: "1.1rem", margin: "0 0 6px 0" }}>Forecast many SKUs from a file</h3>
          <p style={{ margin: "0 0 12px 0", fontSize: "0.85rem", color: PALETTE.textDim, lineHeight: 1.55 }}>
            Upload a CSV or Excel file with one row per SKU, location and period, using columns such as{" "}
            <code style={{ color: PALETTE.textMuted }}>sku_id, location_id, period, units</code>. The
            demand_history templates work too. Each series gets its own detected cycle and its own band.
            Up to 200 series per file.
          </p>
        </>
      )}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 12,
          alignItems: "flex-end",
          padding: "0.9rem 1rem",
          backgroundColor: PALETTE.bgPanel,
          border: `1px solid ${PALETTE.border}`,
          borderRadius: 8,
        }}
      >
        {!givenFile && (
          <label style={labelWrap}>
            <span style={labelStyle}>File (.csv or .xlsx)</span>
            <input
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              style={{ color: PALETTE.text, fontSize: "0.8rem", maxWidth: 260 }}
            />
          </label>
        )}
        <label style={labelWrap}>
          <span style={labelStyle}>Season</span>
          <select
            value={String(season)}
            onChange={(e) => setSeason(parseSeasonChoice(e.target.value))}
            style={inputStyle}
          >
            {SEASON_OPTIONS.map((o) => (
              <option key={String(o.value)} value={String(o.value)}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label style={labelWrap}>
          <span style={labelStyle}>Periods ahead</span>
          <input
            type="number"
            min={1}
            max={MAX_HORIZON}
            value={horizon}
            onChange={(e) => setHorizon(clampHorizon(Number(e.target.value)))}
            style={{ ...inputStyle, width: 80 }}
          />
        </label>
        <button
          onClick={() => void run()}
          disabled={busy}
          style={{
            padding: "8px 14px",
            fontSize: "0.82rem",
            fontWeight: 700,
            color: PALETTE.accentText,
            backgroundColor: PALETTE.accent,
            border: "none",
            borderRadius: 6,
            cursor: busy ? "wait" : "pointer",
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? "Forecasting…" : givenFile ? "Forecast again" : "Forecast file"}
        </button>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            marginTop: 10,
            padding: "0.6rem 0.8rem",
            backgroundColor: PALETTE.errorBg,
            border: `1px solid ${PALETTE.errorBorder}`,
            borderRadius: 6,
            color: PALETTE.error,
            fontSize: "0.82rem",
          }}
        >
          {error}{" "}
          {error.includes(`${PLAN.plan} plan`) && (
            <a href={PLAN.href} style={{ color: PALETTE.link }}>
              {PLAN.linkLabel}
            </a>
          )}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 12 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: "0.82rem", color: PALETTE.textMuted }}>
              Forecast {result.n_forecast} of {result.n_series} series from your{" "}
              {FORMAT_LABEL[result.source_format] ?? "file"}, {result.horizon} periods ahead
              {result.skipped_rows > 0 && `, ${result.skipped_rows} row(s) skipped (no SKU or no number)`}.
            </span>
            <button
              onClick={downloadCsv}
              disabled={result.n_forecast === 0}
              style={{
                padding: "5px 12px",
                fontSize: "0.78rem",
                fontWeight: 700,
                color: PALETTE.text,
                backgroundColor: "transparent",
                border: `1px solid ${PALETTE.border}`,
                borderRadius: 4,
                cursor: result.n_forecast === 0 ? "not-allowed" : "pointer",
              }}
            >
              Download all (CSV)
            </button>
          </div>
          <div style={{ overflowX: "auto", border: `1px solid ${PALETTE.border}`, borderRadius: 6 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem", minWidth: 640 }}>
              <thead>
                <tr style={{ color: PALETTE.textDim, textAlign: "left" }}>
                  <th style={th}>SKU</th>
                  <th style={th}>Location</th>
                  <th style={th}>Periods</th>
                  <th style={th}>Cycle</th>
                  <th style={th}>Next period: median (90% band)</th>
                  <th style={th}>Last forecast period: median</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {result.series.map((s) => {
                  const first = s.band?.[0];
                  const last = s.band?.[s.band.length - 1];
                  return (
                    <tr key={`${s.sku_id}|${s.location_id}`} style={{ borderTop: `1px solid ${PALETTE.border}` }}>
                      <td style={{ ...td, fontFamily: "monospace" }}>{s.sku_id}</td>
                      <td style={{ ...td, fontFamily: "monospace" }}>{s.location_id}</td>
                      <td style={td}>{s.n_points}</td>
                      {s.error ? (
                        <td style={{ ...td, color: PALETTE.warn }} colSpan={4}>
                          {s.error}
                        </td>
                      ) : (
                        <>
                          <td style={td} title={s.settings?.note}>
                            {s.settings && s.settings.season_length > 1 ? `${s.settings.season_length} periods` : "none"}
                            {s.method ? `, ${s.method.toUpperCase()}` : ""}
                          </td>
                          <td style={td}>
                            {first ? `${fmt(first.q50)} (${fmt(first.q05)} to ${fmt(first.q95)})` : "n/a"}
                          </td>
                          <td style={td}>{last ? fmt(last.q50) : "n/a"}</td>
                          <td style={td}>
                            {onPickSeries && (
                              <button
                                onClick={() => {
                                  onPickSeries(s.history);
                                  document.getElementById("dso-forecast")?.scrollIntoView({ behavior: "smooth" });
                                }}
                                style={{
                                  padding: "3px 9px",
                                  fontSize: "0.72rem",
                                  color: PALETTE.link,
                                  backgroundColor: "transparent",
                                  border: `1px solid ${PALETTE.border}`,
                                  borderRadius: 4,
                                  cursor: "pointer",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                Chart it
                              </button>
                            )}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

const labelWrap: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4 };
const labelStyle: React.CSSProperties = {
  fontSize: "0.68rem",
  color: PALETTE.textDim,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};
const inputStyle: React.CSSProperties = {
  padding: "0.4rem",
  borderRadius: 4,
  border: `1px solid ${PALETTE.border}`,
  backgroundColor: PALETTE.bg,
  color: PALETTE.text,
  fontSize: "0.82rem",
};
const th: React.CSSProperties = { padding: "0.45rem 0.6rem", fontWeight: 600, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "0.45rem 0.6rem", color: PALETTE.text, verticalAlign: "top" };
