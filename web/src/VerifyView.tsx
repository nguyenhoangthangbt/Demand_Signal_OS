// VerifyView — the normalized trust-gate surface for DemandSignalOS
// (DECISIONS_LOG §P #65), ported from the SimOS reference VerifyPanel/VerifyPage.
//
// Renders a signed CalibrationReceipt (forecast-trust checks) as a self-serve
// "verify it yourself" gate: status pill, per-check table with the audit
// formula + recompute PASS/FAIL, provenance, the HMAC signature
// (tamper-evidence), caveats, and a download-workbook button.
//
// Self-contained, inline-styled to match the existing App.tsx PALETTE. Fetches
// GET /api/v1/calibration/receipt/example from the thin DSO API; falls back to
// the bundled real signed example (verifyExample.json) when offline.

import { useEffect, useMemo, useState } from "react";
import bundledExample from "./verifyExample.json";

// API base: VITE_DSO_API_BASE if set, else same-origin /api/v1.
const API_BASE: string =
  (import.meta.env.VITE_DSO_API_BASE as string | undefined) ?? "/api/v1";

const PALETTE = {
  bg: "#0f172a",
  bgPanel: "#1e293b",
  border: "#334155",
  text: "#f8fafc",
  textMuted: "#cbd5e1",
  textDim: "#94a3b8",
  textFaint: "#64748b",
  accent: "#fbbf24",
  link: "#7dd3fc",
  ok: "#86efac",
  okBg: "#14321f",
  okBorder: "#166534",
  error: "#fca5a5",
  errorBg: "#3f1d1d",
  errorBorder: "#7f1d1d",
} as const;

type Metric = {
  name: string;
  measured_value: number;
  reference_value: number | null;
  tolerance: number;
  tolerance_kind?: string;
  direction: "higher_better" | "lower_better" | "match";
  gate?: string;
  formula?: string;
};
type Phase = { phase_id: string; title: string; metrics: Metric[] };
export type TrustReceipt = {
  calibration_id: string;
  phases: Phase[];
  provenance?: {
    engine?: string;
    engine_version?: string;
    produced_at?: string;
    seed?: number;
  };
  inputs_hash?: string;
  outputs_hash?: string;
  signature?: string | null;
  signed_by?: string | null;
  key_version?: number;
  caveats?: string[];
  upstream_receipt_refs?: string[];
};

// Recompute pass/fail in the browser — same logic as the SimOS reference, so a
// reader can audit the verdict client-side without trusting the server.
function metricPasses(m: Metric): boolean {
  const r = m.reference_value;
  if (m.tolerance === 0) return Math.abs(m.measured_value - (r ?? 0)) <= 1e-7;
  if (m.direction === "higher_better")
    return r == null ? true : m.measured_value >= r - m.tolerance;
  if (m.direction === "lower_better")
    return r == null
      ? m.measured_value <= m.tolerance
      : m.measured_value <= r + m.tolerance;
  return Math.abs(m.measured_value - (r ?? 0)) <= m.tolerance;
}

function Panel({
  receipt,
  onDownloadWorkbook,
}: {
  receipt: TrustReceipt;
  onDownloadWorkbook: () => void;
}) {
  const metrics = useMemo(
    () =>
      receipt.phases.flatMap((p) =>
        p.metrics.map((m) => ({ phase: p.title, m })),
      ),
    [receipt],
  );
  const allPass = metrics.every(({ m }) => metricPasses(m));
  const hardFails = metrics.filter(
    ({ m }) => (m.gate ?? "hard") === "hard" && !metricPasses(m),
  ).length;
  const engine = receipt.provenance?.engine ?? "engine";

  const cellTh: React.CSSProperties = {
    padding: "0 12px 8px 0",
    fontSize: "0.65rem",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: PALETTE.textFaint,
    textAlign: "left",
  };
  const cellTd: React.CSSProperties = {
    padding: "8px 12px 8px 0",
    fontSize: "0.85rem",
    borderTop: `1px solid ${PALETTE.border}`,
    verticalAlign: "top",
  };

  return (
    <div
      style={{
        border: `1px solid ${PALETTE.border}`,
        borderRadius: 10,
        backgroundColor: PALETTE.bgPanel,
        overflow: "hidden",
      }}
    >
      {/* Status header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          padding: "14px 16px",
          borderBottom: `1px solid ${PALETTE.border}`,
        }}
      >
        <div>
          <div style={{ fontSize: "0.95rem", fontWeight: 700, color: PALETTE.text }}>
            {allPass ? "✓ Verified" : "✕ Verification failed"} — {engine}
          </div>
          <div style={{ fontSize: "0.72rem", color: PALETTE.textFaint, marginTop: 2 }}>
            {metrics.length} checks · {hardFails} hard failures ·{" "}
            {receipt.calibration_id}
          </div>
        </div>
        <span
          style={{
            borderRadius: 999,
            padding: "4px 14px",
            fontSize: "0.72rem",
            fontWeight: 700,
            backgroundColor: allPass ? PALETTE.okBg : PALETTE.errorBg,
            color: allPass ? PALETTE.ok : PALETTE.error,
            border: `1px solid ${allPass ? PALETTE.okBorder : PALETTE.errorBorder}`,
          }}
        >
          {allPass ? "PASS" : "FAIL"}
        </span>
      </div>

      {/* Per-check table */}
      <div style={{ overflowX: "auto", padding: "12px 16px" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={cellTh}>Check</th>
              <th style={{ ...cellTh, textAlign: "right" }}>Measured</th>
              <th style={{ ...cellTh, textAlign: "right" }}>Reference</th>
              <th style={{ ...cellTh, textAlign: "right" }}>Tolerance</th>
              <th style={cellTh}>Audit formula</th>
              <th style={{ ...cellTh, textAlign: "right" }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map(({ phase, m }, i) => {
              const pass = metricPasses(m);
              return (
                <tr key={i}>
                  <td style={cellTd}>
                    <div style={{ fontWeight: 600, color: PALETTE.textMuted }}>
                      {m.name}
                    </div>
                    <div style={{ fontSize: "0.68rem", color: PALETTE.textFaint }}>
                      {phase}
                    </div>
                  </td>
                  <td
                    style={{
                      ...cellTd,
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      color: PALETTE.text,
                    }}
                  >
                    {m.measured_value}
                  </td>
                  <td
                    style={{
                      ...cellTd,
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      color: PALETTE.textDim,
                    }}
                  >
                    {m.reference_value ?? "—"}
                  </td>
                  <td
                    style={{
                      ...cellTd,
                      textAlign: "right",
                      fontVariantNumeric: "tabular-nums",
                      color: PALETTE.textDim,
                    }}
                  >
                    {m.tolerance}
                  </td>
                  <td
                    style={{
                      ...cellTd,
                      fontSize: "0.75rem",
                      color: PALETTE.textDim,
                      fontFamily: "monospace",
                    }}
                  >
                    {m.formula ?? m.name}
                  </td>
                  <td style={{ ...cellTd, textAlign: "right" }}>
                    <span
                      style={{
                        fontWeight: 700,
                        color: pass ? PALETTE.ok : PALETTE.error,
                      }}
                    >
                      {pass ? "PASS" : "FAIL"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Caveats */}
      {receipt.caveats && receipt.caveats.length > 0 && (
        <div
          style={{
            borderTop: `1px solid ${PALETTE.border}`,
            padding: "10px 16px",
          }}
        >
          <div
            style={{
              fontSize: "0.68rem",
              fontWeight: 700,
              color: PALETTE.textFaint,
              textTransform: "uppercase",
            }}
          >
            Caveats
          </div>
          <ul
            style={{
              margin: "6px 0 0 0",
              paddingLeft: 18,
              fontSize: "0.75rem",
              color: PALETTE.textDim,
              lineHeight: 1.5,
            }}
          >
            {receipt.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Provenance + signature + download */}
      <div
        style={{
          borderTop: `1px solid ${PALETTE.border}`,
          padding: "12px 16px",
          fontSize: "0.7rem",
          color: PALETTE.textFaint,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 4,
          }}
        >
          <span>
            seed: <b style={{ color: PALETTE.textDim }}>{receipt.provenance?.seed ?? "—"}</b>
          </span>
          <span>
            produced:{" "}
            <b style={{ color: PALETTE.textDim }}>
              {receipt.provenance?.produced_at?.slice(0, 19) ?? "—"}
            </b>
          </span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            inputs_hash:{" "}
            <b style={{ color: PALETTE.textDim }}>
              {receipt.inputs_hash?.slice(0, 22) ?? "—"}…
            </b>
          </span>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            outputs_hash:{" "}
            <b style={{ color: PALETTE.textDim }}>
              {receipt.outputs_hash?.slice(0, 22) ?? "—"}…
            </b>
          </span>
        </div>
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          signature (HMAC-SHA256, {receipt.signed_by ?? "unsigned"}):{" "}
          <span style={{ fontFamily: "monospace", color: PALETTE.accent }}>
            {receipt.signature
              ? receipt.signature.slice(0, 32) + "…"
              : "— not signed —"}
          </span>
        </div>
        <button
          onClick={onDownloadWorkbook}
          style={{
            marginTop: 4,
            width: "fit-content",
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            borderRadius: 6,
            backgroundColor: PALETTE.link,
            color: PALETTE.bg,
            padding: "7px 14px",
            fontSize: "0.78rem",
            fontWeight: 700,
            border: "none",
            cursor: "pointer",
          }}
        >
          ↓ Download validation workbook (.xlsx)
        </button>
      </div>
    </div>
  );
}

export default function VerifyView() {
  const [receipt, setReceipt] = useState<TrustReceipt>(
    bundledExample as unknown as TrustReceipt,
  );
  const [isExample, setIsExample] = useState(true);
  const [live, setLive] = useState(false);
  const [raw, setRaw] = useState("");
  const [error, setError] = useState("");

  // Fetch a fresh signed receipt from the live DSO API. On any failure we keep
  // the bundled real signed example — same shape, no backend round-trip.
  useEffect(() => {
    fetch(`${API_BASE}/calibration/receipt/example`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("offline"))))
      .then((data) => {
        setReceipt(data);
        setIsExample(true);
        setLive(true);
      })
      .catch(() => {
        /* keep bundled example */
      });
  }, []);

  function loadFromText(text: string) {
    setError("");
    try {
      const parsed = JSON.parse(text);
      if (!parsed.phases || !Array.isArray(parsed.phases))
        throw new Error("not a receipt (no phases[])");
      setReceipt(parsed);
      setIsExample(false);
      setLive(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function downloadWorkbook() {
    // Generate the workbook server-side from the exact receipt shown.
    try {
      const r = await fetch(`${API_BASE}/calibration/receipt/xlsx`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(receipt),
      });
      if (!r.ok) throw new Error("xlsx export failed");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${receipt.calibration_id}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    } catch {
      // Offline fallback: download the receipt JSON so the user still has the
      // signed artifact to verify out-of-band.
      const blob = new Blob([JSON.stringify(receipt, null, 2)], {
        type: "application/json",
      });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${receipt.calibration_id}.json`;
      a.click();
    }
  }

  return (
    <section style={{ padding: "2rem 1.5rem", maxWidth: 860, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h2 style={{ margin: 0, fontSize: "1.5rem", color: PALETTE.text }}>
          Verify a forecast result
        </h2>
        {live && (
          <span
            style={{
              borderRadius: 999,
              backgroundColor: "#0c2a3f",
              color: PALETTE.link,
              padding: "2px 10px",
              fontSize: "0.65rem",
              fontWeight: 700,
            }}
          >
            live · signed by the engine
          </span>
        )}
      </div>
      <p
        style={{
          marginTop: 8,
          fontSize: "0.9rem",
          color: PALETTE.textDim,
          lineHeight: 1.6,
          maxWidth: 680,
        }}
      >
        Every DemandSignalOS forecast ships a signed trust receipt — interval
        coverage, CRPS-vs-baseline, and drift checks you can re-derive yourself.
        Below is a real receipt from an operational (H+4w) run on SKU-4471 @
        DC-EAST. Paste your own receipt to verify it, or download the validation
        workbook and recompute every check in Excel.
      </p>

      <div style={{ marginTop: 20 }}>
        <Panel receipt={receipt} onDownloadWorkbook={downloadWorkbook} />
      </div>

      <details
        style={{
          marginTop: 20,
          border: `1px solid ${PALETTE.border}`,
          borderRadius: 8,
          padding: 14,
        }}
      >
        <summary
          style={{
            cursor: "pointer",
            fontSize: "0.85rem",
            fontWeight: 600,
            color: PALETTE.textMuted,
          }}
        >
          Verify a different receipt (paste JSON)
        </summary>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          placeholder='{"calibration_id": "...", "phases": [...], ...}'
          style={{
            marginTop: 12,
            height: 130,
            width: "100%",
            boxSizing: "border-box",
            borderRadius: 6,
            border: `1px solid ${PALETTE.border}`,
            backgroundColor: PALETTE.bg,
            color: PALETTE.textMuted,
            padding: 8,
            fontFamily: "monospace",
            fontSize: "0.72rem",
          }}
        />
        <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={() => loadFromText(raw)}
            style={{
              borderRadius: 6,
              backgroundColor: PALETTE.link,
              color: PALETTE.bg,
              padding: "7px 16px",
              fontSize: "0.8rem",
              fontWeight: 700,
              border: "none",
              cursor: "pointer",
            }}
          >
            Verify
          </button>
          {!isExample && (
            <button
              onClick={() => {
                setReceipt(bundledExample as unknown as TrustReceipt);
                setIsExample(true);
              }}
              style={{
                background: "none",
                border: "none",
                color: PALETTE.textDim,
                fontSize: "0.8rem",
                cursor: "pointer",
              }}
            >
              Back to example
            </button>
          )}
          {error && (
            <span style={{ fontSize: "0.8rem", color: PALETTE.error }}>{error}</span>
          )}
        </div>
      </details>
    </section>
  );
}
