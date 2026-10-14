// Quick-forecast settings the user can see and change (audit finding C-05).
//
// The page used to send season_length 7, horizon 8 and method ets on every
// call, so a monthly series with a Q4 peak forecast flat. "auto" asks the
// engine to detect the cycle from the data and to pick a method that can
// carry it; the response reports what it used.

export type SeasonChoice = "auto" | number;

export const SEASON_OPTIONS: { value: SeasonChoice; label: string }[] = [
  { value: "auto", label: "Detect from my data" },
  { value: 1, label: "No repeating cycle" },
  { value: 4, label: "4 (quarterly in monthly data)" },
  { value: 7, label: "7 (weekly in daily data)" },
  { value: 12, label: "12 (yearly in monthly data)" },
  { value: 13, label: "13 (quarterly in weekly data)" },
  { value: 52, label: "52 (yearly in weekly data)" },
];

export const DEFAULT_HORIZON = 8;
export const MAX_HORIZON = 24; // the engine's per-step band cap

export function clampHorizon(h: number): number {
  if (!Number.isFinite(h)) return DEFAULT_HORIZON;
  return Math.min(MAX_HORIZON, Math.max(1, Math.round(h)));
}

export function parseSeasonChoice(raw: string): SeasonChoice {
  return raw === "auto" ? "auto" : Math.max(1, Math.round(Number(raw)) || 1);
}

/** The settings part of every /forecast/single* request body. */
export function forecastRequestSettings(season: SeasonChoice, horizon: number) {
  return {
    horizon: clampHorizon(horizon),
    season_length: season,
    method_id: "auto",
  };
}

/** What the engine reports back under `settings` on /forecast/single. */
export interface ResolvedSettings {
  season_length: number;
  season_source: "detected" | "given";
  season_strength: number | null;
  method_id: string;
  method_source: "auto" | "given";
  note: string;
}

const METHOD_NAMES: Record<string, string> = {
  ets: "ETS (exponential smoothing)",
  ces: "CES (complex exponential smoothing)",
  arima: "ARIMA",
  theta: "Theta",
};

/** One plain sentence describing the settings the forecast used. */
export function describeSettings(s: ResolvedSettings | null | undefined): string {
  if (!s) return "";
  const method = METHOD_NAMES[s.method_id] ?? s.method_id;
  const season =
    s.season_length > 1
      ? `a ${s.season_length}-period cycle${s.season_source === "detected" ? " (detected)" : ""}`
      : "no repeating cycle";
  return `Used ${method} with ${season}.`;
}
