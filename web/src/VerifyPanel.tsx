/**
 * VerifyPanel — canonical trust-gate "verify it yourself" surface (DECISIONS_LOG §P #65).
 *
 * ONE self-contained component, vendored VERBATIM into every engine web app
 * (SimOS, O2C, PlanningOS, DSO) so the trust seal looks and reads identically
 * everywhere. It renders a signed CalibrationReceipt (from any engine — the
 * contract is normalized) as a signed *certificate*:
 *   - a plain-language verdict a practitioner / CFO actually understands,
 *   - a per-check table an auditor can re-derive (technical name + audit formula),
 *   - a tamper-evident HMAC signature.
 *
 * Fixed light "certificate" theme so it reads as an inset document on any app
 * background (light Fiori or dark dashboard) and is byte-identical across apps.
 * No external UI deps (no tailwind / lucide / UI5) — inline styles + inline SVG.
 *
 * Pure function of the receipt JSON. DO NOT fork per app: edit this canonical
 * copy under docs_v1/design/trust_gate_verify_panel/ and re-vendor to all four.
 */
import { useMemo } from 'react'

type Metric = {
  name: string
  measured_value: number
  reference_value: number | null
  tolerance: number
  tolerance_kind?: string
  direction: 'higher_better' | 'lower_better' | 'match'
  gate?: string
  formula?: string
}
type Phase = { phase_id: string; title: string; metrics: Metric[] }
export type TrustReceipt = {
  calibration_id: string
  phases: Phase[]
  provenance?: { engine?: string; engine_version?: string; produced_at?: string; seed?: number | null }
  inputs_hash?: string
  outputs_hash?: string
  signature?: string | null
  signed_by?: string | null
  key_version?: number
  caveats?: string[]
  upstream_receipt_refs?: string[]
}

// Friendly engine label + the noun used in the plain-language verdict sentence.
const ENGINE: Record<string, { label: string; noun: string }> = {
  simulationos: { label: 'SimulationOS', noun: 'simulation' },
  order2cash: { label: 'Order2Cash', noun: 'order-to-cash run' },
  planningos: { label: 'PlanningOS', noun: 'plan' },
  demandsignal: { label: 'DemandSignalOS', noun: 'forecast' },
}

// Plain-language meaning per check, keyed by the engine's check name. The
// technical name + audit formula stay on screen for auditors; THIS sentence is
// what a practitioner reads. Unknown names (e.g. user-pasted receipts) simply
// fall back to no plain line — never an error.
const CHECK_COPY: Record<string, string> = {
  // SimOS — run trust
  'determinism (rerun byte-delta)': 'Re-running the model gives byte-for-byte identical results: the same inputs always produce the same answer.',
  'conservation (created-completed-WIP)': 'Every entity is accounted for: nothing created was lost or double-counted.',
  'littles_law (avg_queue vs lambda*W)': "Queue lengths obey the textbook arrival-rate x wait-time law (Little's Law): the engine's physics check out.",
  // O2C — execution trust
  'order_count replay match': 'Replaying the event log reproduces the exact order count from the source system.',
  'return_rate_pct match': 'The return rate computed from events matches the source records within tolerance.',
  'ledger arithmetic (AR balance)': 'Invoices minus payments equal the accounts-receivable balance to the cent: the books balance.',
  // PlanningOS — decision trust
  'FSD over baseline (P(plan>=base))': 'The recommended plan beats the baseline in every scenario, not just on average (first-order stochastic dominance).',
  'Barlas behaviour validity (failed/total)': "The model reproduces the real system's behaviour on every standard validity check (Barlas 1996).",
  '95% CI half-width / mean': 'The result is precise: its 95% confidence interval is tight relative to the value.',
  // DSO — forecast trust
  '90% interval coverage': "Actual demand fell inside the forecast's predicted range about as often as promised (~90%).",
  'CRPS vs baseline (ratio)': 'The forecast scores better than a naive baseline on calibrated probabilistic accuracy.',
  'drift magnitude (<1.5 = stable)': "Recent accuracy hasn't degraded: the forecast is stable, not drifting.",
}

function metricPasses(m: Metric): boolean {
  const r = m.reference_value
  if (m.tolerance === 0) return Math.abs(m.measured_value - (r ?? 0)) <= 1e-7
  if (m.direction === 'higher_better') return r == null ? true : m.measured_value >= r - m.tolerance
  if (m.direction === 'lower_better') return r == null ? m.measured_value <= m.tolerance : m.measured_value <= r + m.tolerance
  return Math.abs(m.measured_value - (r ?? 0)) <= m.tolerance
}

function fmtDate(iso?: string): string {
  if (!iso) return 'n/a'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso.slice(0, 19)
  const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()]
  const p = (n: number) => String(n).padStart(2, '0')
  return `${mon} ${d.getUTCDate()}, ${d.getUTCFullYear()} · ${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`
}

const fmtNum = (n: number | null): string =>
  n == null ? 'n/a' : Number.isInteger(n) ? String(n) : String(Math.round(n * 1e6) / 1e6)

// ---- fixed "certificate" palette (theme-independent) ------------------------
const C = {
  card: '#ffffff', ink: '#0f172a', sub: '#475569', faint: '#94a3b8',
  line: '#e2e8f0', wash: '#f8fafc',
  okBg: '#ecfdf5', okInk: '#047857', okLine: '#a7f3d0',
  noBg: '#fef2f2', noInk: '#b91c1c', noLine: '#fecaca',
  accent: '#2563eb',
}

function Shield({ ok }: { ok: boolean }) {
  return (
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 2 4 5v6c0 5 3.4 8.3 8 11 4.6-2.7 8-6 8-11V5l-8-3Z"
        fill={ok ? C.okBg : C.noBg} stroke={ok ? C.okInk : C.noInk} strokeWidth="1.4" />
      {ok
        ? <path d="m8.5 12 2.3 2.3L15.5 9.5" stroke={C.okInk} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        : <path d="M12 7.5v5M12 15.5v.6" stroke={C.noInk} strokeWidth="1.8" strokeLinecap="round" />}
    </svg>
  )
}

export default function VerifyPanel({
  receipt,
  onDownloadWorkbook,
}: {
  receipt: TrustReceipt
  onDownloadWorkbook?: () => void
}) {
  const rows = useMemo(
    () => receipt.phases.flatMap((p) => p.metrics.map((m) => ({ phase: p.title, m }))),
    [receipt],
  )
  const allPass = rows.every(({ m }) => metricPasses(m))
  const failCount = rows.filter(({ m }) => !metricPasses(m)).length
  const hardFails = rows.filter(({ m }) => (m.gate ?? 'hard') === 'hard' && !metricPasses(m)).length
  const eng = ENGINE[receipt.provenance?.engine ?? ''] ?? { label: receipt.provenance?.engine ?? 'engine', noun: 'result' }
  const seed = receipt.provenance?.seed

  const takeaway = allPass
    ? `All ${rows.length} trust checks passed — you can rely on this ${eng.noun}.`
    : `${hardFails || failCount} of ${rows.length} checks failed — treat this ${eng.noun} with caution until resolved.`

  return (
    <div style={{
      background: C.card, color: C.ink, border: `1px solid ${C.line}`, borderRadius: 14,
      boxShadow: '0 1px 2px rgba(15,23,42,.06), 0 8px 24px rgba(15,23,42,.06)',
      fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', overflow: 'hidden', textAlign: 'left',
    }}>
      {/* Verdict header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '16px 18px', borderBottom: `1px solid ${C.line}` }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <Shield ok={allPass} />
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>
              {allPass ? 'Verified' : 'Verification failed'} <span style={{ color: C.faint, fontWeight: 600 }}>· {eng.label}</span>
            </div>
            <div style={{ fontSize: 13.5, color: C.sub, marginTop: 2, maxWidth: 560 }}>{takeaway}</div>
            <div style={{ fontSize: 11, color: C.faint, marginTop: 4, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
              {rows.length} checks · {hardFails} hard failures · {receipt.calibration_id}
            </div>
          </div>
        </div>
        <span style={{
          flexShrink: 0, padding: '5px 12px', borderRadius: 999, fontSize: 12.5, fontWeight: 800, letterSpacing: .3,
          background: allPass ? C.okBg : C.noBg, color: allPass ? C.okInk : C.noInk,
          border: `1px solid ${allPass ? C.okLine : C.noLine}`,
        }}>{allPass ? 'PASS' : 'FAIL'}</span>
      </div>

      {/* Checks */}
      <div style={{ padding: '6px 10px 10px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
          <thead>
            <tr style={{ color: C.faint, fontSize: 11, textTransform: 'uppercase', letterSpacing: .5 }}>
              <th style={{ textAlign: 'left', padding: '8px 8px' }}>What was checked</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', whiteSpace: 'nowrap' }}>Measured</th>
              <th style={{ textAlign: 'right', padding: '8px 8px', whiteSpace: 'nowrap' }}>Target</th>
              <th style={{ textAlign: 'right', padding: '8px 8px' }}>Result</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ m }, i) => {
              const pass = metricPasses(m)
              const plain = CHECK_COPY[m.name]
              return (
                <tr key={i} style={{ borderTop: `1px solid ${C.line}` }}>
                  <td style={{ padding: '10px 8px', verticalAlign: 'top' }}>
                    <div style={{ fontWeight: 600, color: C.ink }}>{m.name}</div>
                    {plain && <div style={{ color: C.sub, marginTop: 2, lineHeight: 1.4, maxWidth: 520 }}>{plain}</div>}
                    {m.formula && (
                      <div style={{ color: C.faint, marginTop: 3, fontSize: 11.5, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                        formula: {m.formula}
                      </div>
                    )}
                  </td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', verticalAlign: 'top', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{fmtNum(m.measured_value)}</td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', verticalAlign: 'top', fontVariantNumeric: 'tabular-nums', color: C.sub }}>
                    {fmtNum(m.reference_value)}
                    {m.tolerance ? <span style={{ color: C.faint }}> ±{fmtNum(m.tolerance)}</span> : null}
                  </td>
                  <td style={{ padding: '10px 8px', textAlign: 'right', verticalAlign: 'top' }}>
                    <span style={{ fontWeight: 700, color: pass ? C.okInk : C.noInk }}>{pass ? 'PASS' : 'FAIL'}</span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Caveats */}
      {receipt.caveats && receipt.caveats.length > 0 && (
        <div style={{ padding: '10px 18px', borderTop: `1px solid ${C.line}`, background: C.wash }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: C.faint, textTransform: 'uppercase', letterSpacing: .5 }}>Caveats</div>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: C.sub, fontSize: 12.5 }}>
            {receipt.caveats.map((c, i) => <li key={i} style={{ marginTop: 2 }}>{c}</li>)}
          </ul>
        </div>
      )}

      {/* Provenance */}
      <div style={{ padding: '12px 18px', borderTop: `1px solid ${C.line}`, fontSize: 11.5, color: C.sub, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 16px' }}>
        <span>produced: <b style={{ color: C.ink }}>{fmtDate(receipt.provenance?.produced_at)}</b></span>
        {seed != null && <span>seed: <b style={{ color: C.ink }}>{seed}</b></span>}
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>inputs: <span style={{ fontFamily: 'ui-monospace, monospace' }}>{receipt.inputs_hash?.slice(0, 22) ?? 'n/a'}…</span></span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>outputs: <span style={{ fontFamily: 'ui-monospace, monospace' }}>{receipt.outputs_hash?.slice(0, 22) ?? 'n/a'}…</span></span>
      </div>

      {/* Tamper-evident seal */}
      <div style={{ padding: '12px 18px', borderTop: `1px solid ${C.line}`, background: C.wash }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, fontWeight: 600, color: C.ink }}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
            <rect x="5" y="11" width="14" height="9" rx="2" fill={C.okBg} stroke={C.okInk} strokeWidth="1.4" />
            <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke={C.okInk} strokeWidth="1.4" />
          </svg>
          Tamper-evident seal
        </div>
        <div style={{ fontSize: 11.5, color: C.sub, marginTop: 3 }}>
          Cryptographically signed by the engine ({receipt.signed_by ?? 'unsigned'}, HMAC-SHA256). Any edit to this receipt breaks the seal.
        </div>
        <div style={{ fontSize: 11, color: C.faint, marginTop: 3, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {receipt.signature ? receipt.signature.slice(0, 40) + '…' : '— not signed —'}
        </div>
        {onDownloadWorkbook && (
          <>
            <button onClick={onDownloadWorkbook} style={{
              marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 8, cursor: 'pointer',
              background: C.accent, color: '#fff', border: 'none', borderRadius: 9, padding: '8px 13px', fontSize: 12.5, fontWeight: 700,
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Download validation workbook (.xlsx)
            </button>
            <div style={{ fontSize: 11, color: C.faint, marginTop: 5 }}>Re-derive every check yourself in Excel — live formulas recompute each PASS/FAIL.</div>
          </>
        )}
      </div>
    </div>
  )
}
