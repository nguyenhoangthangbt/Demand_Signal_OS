// How the leaderboard winner is presented (audit findings C-09, F-21, E-07).
//
// A model can beat the naive benchmarks on CRPS while its band is far too
// narrow: the golden FACE-CRM winner's 90% band caught 50% of actuals (its
// 50% band 25%), yet the page showed a green "Winner ... beats all naive
// benchmarks". The engine now reports interval_calibration per entry; this
// turns it into the banner tone and wording.

export type Calibration = "ok" | "too_narrow" | "too_wide" | "unknown";

export interface VerdictInput {
  winner_method_id: string;
  winner_is_benchmark: boolean;
  winner_interval_calibration?: Calibration;
  crps?: number;
  coverage_50?: number | null;
  coverage_90?: number | null;
}

export interface Verdict {
  tone: "good" | "caution" | "bad";
  headline: string;
  detail: string;
}

const pct = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "n/a" : `${Math.round(v * 100)}%`;

export function winnerVerdict(r: VerdictInput): Verdict {
  if (r.winner_is_benchmark) {
    return {
      tone: "bad",
      headline: `No forecaster beat the naive benchmarks. Recommending the safest baseline: ${r.winner_method_id}.`,
      detail:
        "Your series may be too short or too noisy for a model to add value. That is an honest answer, not a failure.",
    };
  }
  const crps = r.crps != null ? ` (CRPS ${r.crps.toFixed(3)})` : "";
  const cov = `Its 90% band caught ${pct(r.coverage_90)} of actuals in the backtest and its 50% band ${pct(r.coverage_50)}.`;
  if (r.winner_interval_calibration === "too_narrow") {
    return {
      tone: "caution",
      headline: `Lowest error: ${r.winner_method_id}${crps}, and it beats the naive benchmarks. Its band is too narrow.`,
      detail:
        `${cov} An honest band catches about 90% and 50%. Treat its q05 to q95 range as optimistic: ` +
        "safety stock set from it will under-protect. Add history or check another method's coverage before you rely on the band.",
    };
  }
  if (r.winner_interval_calibration === "too_wide") {
    return {
      tone: "caution",
      headline: `Lowest error: ${r.winner_method_id}${crps}, and it beats the naive benchmarks. Its band is wider than it needs to be.`,
      detail: `${cov} Safety stock set from it will over-protect.`,
    };
  }
  return {
    tone: "good",
    headline: `Winner: ${r.winner_method_id}${crps}, beats all naive benchmarks.`,
    detail: r.winner_interval_calibration === "ok" ? `${cov} The band keeps its promise.` : cov,
  };
}
