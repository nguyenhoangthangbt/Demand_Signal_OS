// "Send to SimOS" panel (customer journey 2026-10-12, finding C-01).
//
// Before this panel, the SimOS downloads read every forecast value as "orders
// per day", so a monthly forecast reached SimOS about 30 times too high, with no
// warning. Now the customer states what one number means, sees the converted
// orders per hour, confirms, and only then downloads. Used by the quick forecast
// (POST endpoints, the posted series) and by a finished leaderboard run (GET
// endpoints, by run id).

import { useEffect, useState, type CSSProperties } from "react";
import {
  INITIAL_FORM,
  basisQuery,
  fmtNumber,
  headline,
  plainError,
  toBasis,
  type DataFrequency,
  type HandoffBasis,
  type HandoffForm,
  type HandoffPreview,
} from "./lib/simosHandoff";

const C = {
  bgPanel: "#1e293b",
  bgInput: "#0f172a",
  border: "#334155",
  text: "#f8fafc",
  textMuted: "#cbd5e1",
  textDim: "#94a3b8",
  accent: "#fbbf24",
  accentText: "#0f172a",
  ok: "#86efac",
  warn: "#fcd34d",
} as const;

export type HandoffSource =
  | {
      kind: "series";
      apiBase: string;
      // The forecast request without the hand-off (history, horizon, ...).
      body: Record<string, unknown>;
    }
  | {
      kind: "leaderboard";
      apiBase: string;
      runId: string;
      headers: () => Record<string, string>;
      // P0-11 cookie mode: "include" so the session cookie rides along.
      credentials?: () => RequestCredentials | undefined;
    };

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function fetchPreview(source: HandoffSource, basis: HandoffBasis): Promise<HandoffPreview> {
  const r =
    source.kind === "series"
      ? await fetch(`${source.apiBase}/forecast/single.simos.preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...source.body, handoff: basis }),
        })
      : await fetch(
          `${source.apiBase}/forecast/leaderboard/${source.runId}/arrivals.preview?${basisQuery(basis)}`,
          { headers: source.headers(), credentials: source.credentials?.() },
        );
  if (!r.ok) throw new HandoffError(r.status);
  return (await r.json()) as HandoffPreview;
}

class HandoffError extends Error {
  status: number | null;
  constructor(status: number | null) {
    super(plainError(status));
    this.status = status;
  }
}

const FREQ_OPTIONS: { value: DataFrequency; label: string }[] = [
  { value: "day", label: "Day" },
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
];

export default function SimosHandoffPanel({ source }: { source: HandoffSource }) {
  const [form, setForm] = useState<HandoffForm>(INITIAL_FORM);
  const [preview, setPreview] = useState<HandoffPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const parsed = toBasis(form);
  const basis = "basis" in parsed ? parsed.basis : null;
  const basisKey = basis ? JSON.stringify(basis) : "";
  const sourceKey =
    source.kind === "series" ? JSON.stringify(source.body) : `lb:${source.runId}`;

  // Recompute the converted rates whenever the basis or the forecast changes.
  // Any change clears the confirmation: the customer confirms what they see.
  useEffect(() => {
    setConfirmed(false);
    setPreview(null);
    setError(null);
    if (!basis) return;
    let live = true;
    setLoading(true);
    fetchPreview(source, basis)
      .then((p) => live && setPreview(p))
      .catch((e) => live && setError(e instanceof HandoffError ? e.message : plainError(null)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basisKey, sourceKey]);

  const download = async (kind: "yaml" | "xlsx") => {
    if (!basis) return;
    setError(null);
    try {
      let r: Response;
      if (source.kind === "series") {
        r = await fetch(
          `${source.apiBase}/forecast/${kind === "yaml" ? "single.yaml" : "single.simos.xlsx"}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...source.body, handoff: basis }),
          },
        );
      } else {
        r = await fetch(
          `${source.apiBase}/forecast/leaderboard/${source.runId}/arrivals.yaml?${basisQuery(basis)}`,
          { headers: source.headers(), credentials: source.credentials?.() },
        );
      }
      if (!r.ok) throw new HandoffError(r.status);
      const name =
        kind === "yaml"
          ? source.kind === "series"
            ? "dso_arrivals.yaml"
            : `arrivals_${source.runId}.yaml`
          : "dso_simos_arrivals.xlsx";
      saveBlob(await r.blob(), name);
    } catch (e) {
      setError(e instanceof HandoffError ? e.message : plainError(null));
    }
  };

  const set = (patch: Partial<HandoffForm>) => setForm((f) => ({ ...f, ...patch }));
  const canDownload = !!preview && confirmed && !loading;

  const label: CSSProperties = { fontSize: "0.8rem", color: C.textMuted, fontWeight: 600 };
  const input: CSSProperties = {
    width: 72,
    padding: "5px 8px",
    fontSize: "0.8rem",
    color: C.text,
    backgroundColor: C.bgInput,
    border: `1px solid ${C.border}`,
    borderRadius: 4,
  };
  const chip = (on: boolean): CSSProperties => ({
    padding: "5px 12px",
    fontSize: "0.8rem",
    fontWeight: 600,
    color: on ? C.accentText : C.text,
    backgroundColor: on ? C.accent : "transparent",
    border: `1px solid ${on ? C.accent : C.border}`,
    borderRadius: 4,
    cursor: "pointer",
  });
  const dlButton = (primary: boolean): CSSProperties => ({
    padding: "8px 14px",
    fontSize: "0.8rem",
    fontWeight: 600,
    color: primary ? C.accentText : C.text,
    backgroundColor: primary ? C.accent : "transparent",
    border: primary ? "none" : `1px solid ${C.border}`,
    borderRadius: 6,
    cursor: canDownload ? "pointer" : "not-allowed",
    opacity: canDownload ? 1 : 0.5,
  });

  return (
    <div
      data-testid="simos-handoff"
      style={{
        marginBottom: 14,
        padding: "1rem",
        backgroundColor: C.bgPanel,
        border: `1px solid ${C.border}`,
        borderRadius: 8,
      }}
    >
      <h4 style={{ margin: "0 0 4px 0", fontSize: "0.95rem", color: C.text }}>
        Send this forecast to SimOS
      </h4>
      <p style={{ margin: "0 0 12px 0", fontSize: "0.8rem", color: C.textDim }}>
        SimOS models orders arriving per hour. Tell us what one number in your series means; we
        convert it and show the result before you download.
      </p>

      <div style={{ display: "grid", gap: 10 }}>
        <div role="radiogroup" aria-label="Each number in my series is demand per"
          style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={label}>Each number in my series is demand per</span>
          {FREQ_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={form.dataFrequency === o.value}
              onClick={() => set({ dataFrequency: o.value })}
              style={chip(form.dataFrequency === o.value)}
            >
              {o.label}
            </button>
          ))}
        </div>

        <div role="radiogroup" aria-label="The numbers count"
          style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span style={label}>The numbers count</span>
          <button type="button" role="radio" aria-checked={form.demandUnit === "orders"}
            onClick={() => set({ demandUnit: "orders" })} style={chip(form.demandUnit === "orders")}>
            Orders
          </button>
          <button type="button" role="radio" aria-checked={form.demandUnit === "units"}
            onClick={() => set({ demandUnit: "units" })} style={chip(form.demandUnit === "units")}>
            Units
          </button>
          {form.demandUnit === "units" && (
            <label style={{ ...label, fontWeight: 400, display: "flex", gap: 6, alignItems: "center" }}>
              Units per order
              <input type="number" min={0} step="any" value={form.unitsPerOrder}
                onChange={(e) => set({ unitsPerOrder: e.target.value })} style={input} />
            </label>
          )}
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <span style={label}>The site operates</span>
          <label style={{ ...label, fontWeight: 400, display: "flex", gap: 6, alignItems: "center" }}>
            <input type="number" min={1} max={24} step="any" value={form.hoursPerDay}
              onChange={(e) => set({ hoursPerDay: e.target.value })} style={input} />
            hours a day
          </label>
          <label style={{ ...label, fontWeight: 400, display: "flex", gap: 6, alignItems: "center" }}>
            <input type="number" min={1} max={7} step="any" value={form.daysPerWeek}
              onChange={(e) => set({ daysPerWeek: e.target.value })} style={input} />
            days a week
          </label>
        </div>
      </div>

      {"problem" in parsed && (
        <p style={{ margin: "12px 0 0 0", fontSize: "0.8rem", color: C.warn }}>{parsed.problem}</p>
      )}
      {loading && (
        <p style={{ margin: "12px 0 0 0", fontSize: "0.8rem", color: C.textDim }}>
          Converting the forecast...
        </p>
      )}
      {error && (
        <p role="alert" style={{ margin: "12px 0 0 0", fontSize: "0.8rem", color: C.warn }}>
          {error}
        </p>
      )}

      {preview && (
        <div style={{ marginTop: 12 }}>
          <p data-testid="simos-handoff-headline"
            style={{ margin: "0 0 4px 0", fontSize: "0.9rem", color: C.text, fontWeight: 600 }}>
            {headline(preview)}
          </p>
          <p style={{ margin: "0 0 8px 0", fontSize: "0.78rem", color: C.textDim }}>
            {preview.explanation}
          </p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", fontSize: "0.78rem", color: C.textMuted }}>
              <thead>
                <tr>
                  {["Period", "Forecast (median)", "Orders an hour in SimOS"].map((h) => (
                    <th key={h} style={{ textAlign: "right", padding: "4px 10px",
                      borderBottom: `1px solid ${C.border}`, color: C.textDim, fontWeight: 600 }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.steps.map((s) => (
                  <tr key={s.period}>
                    <td style={{ textAlign: "right", padding: "3px 10px" }}>{s.period}</td>
                    <td style={{ textAlign: "right", padding: "3px 10px" }}>
                      {fmtNumber(s.forecast_median, 0)}
                    </td>
                    <td style={{ textAlign: "right", padding: "3px 10px", color: C.text }}>
                      {fmtNumber(s.rate_per_hour, 2, true)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10,
            fontSize: "0.8rem", color: C.text }}>
            <input type="checkbox" checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)} />
            These rates match my operation
          </label>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        {source.kind === "series" && (
          <button type="button" disabled={!canDownload} onClick={() => download("xlsx")}
            title="For SimOS Builder: Import contracts replaces only the arrivals of your open model"
            style={dlButton(true)}>
            Download for SimOS Builder (xlsx)
          </button>
        )}
        <button type="button" disabled={!canDownload} onClick={() => download("yaml")}
          title="For SimOS Builder: Import YAML keeps your model and replaces only its arrivals"
          style={dlButton(source.kind !== "series")}>
          Download SimOS YAML
        </button>
      </div>
      <p style={{ margin: "8px 0 0 0", fontSize: "0.75rem", color: C.textDim }}>
        In SimOS Builder, open your model, then use Import contracts (xlsx) or Import YAML. Only the
        arrivals change; your process steps and resources stay.
      </p>
    </div>
  );
}
