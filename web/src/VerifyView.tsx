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

import { useEffect, useState } from "react";
import bundledExample from "./verifyExample.json";
import VerifyPanel, { type TrustReceipt } from "./VerifyPanel";

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
        <VerifyPanel receipt={receipt} onDownloadWorkbook={downloadWorkbook} />
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
