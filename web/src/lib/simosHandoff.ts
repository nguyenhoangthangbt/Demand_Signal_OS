// DSO -> SimOS hand-off basis (customer journey 2026-10-12, finding C-01).
//
// A forecast value is "demand per period". SimOS needs "orders per hour". The
// conversion depends on facts only the customer knows, so the workbench asks
// for them, shows the converted rate, and only then offers the download. The
// engine does the arithmetic (one source of truth); this module holds the
// form state rules, the request shape and the plain-language messages.

export type DataFrequency = "day" | "week" | "month";
export type DemandUnit = "orders" | "units";

export interface HandoffForm {
  dataFrequency: DataFrequency | null; // null until the customer picks one
  demandUnit: DemandUnit;
  unitsPerOrder: string; // raw input text
  hoursPerDay: string;
  daysPerWeek: string;
}

export const INITIAL_FORM: HandoffForm = {
  dataFrequency: null,
  demandUnit: "orders",
  unitsPerOrder: "1",
  hoursPerDay: "24",
  daysPerWeek: "7",
};

export interface HandoffBasis {
  data_frequency: DataFrequency;
  demand_unit: DemandUnit;
  units_per_order: number;
  operating_hours_per_day: number;
  operating_days_per_week: number;
}

export interface PreviewStep {
  period: number;
  forecast_median: number;
  starts_at_hour: number;
  rate_per_hour: number;
  noise_std: number;
}

export interface HandoffPreview {
  basis: HandoffBasis;
  hours_per_period: number;
  units_per_order: number;
  explanation: string;
  steps: PreviewStep[];
}

// Turn the form into the engine's basis, or a plain message saying what to fix.
export function toBasis(form: HandoffForm): { basis: HandoffBasis } | { problem: string } {
  if (!form.dataFrequency) {
    return { problem: "Choose how long one number in your series covers: a day, a week or a month." };
  }
  const hours = Number(form.hoursPerDay);
  if (!Number.isFinite(hours) || hours <= 0 || hours > 24) {
    return { problem: "Operating hours a day must be more than 0 and at most 24." };
  }
  const days = Number(form.daysPerWeek);
  if (!Number.isFinite(days) || days <= 0 || days > 7) {
    return { problem: "Operating days a week must be more than 0 and at most 7." };
  }
  let upo = 1;
  if (form.demandUnit === "units") {
    upo = Number(form.unitsPerOrder);
    if (!Number.isFinite(upo) || upo <= 0) {
      return { problem: "Units per order must be a number above 0." };
    }
  }
  return {
    basis: {
      data_frequency: form.dataFrequency,
      demand_unit: form.demandUnit,
      units_per_order: upo,
      operating_hours_per_day: hours,
      operating_days_per_week: days,
    },
  };
}

// Query string for the leaderboard GET endpoints (arrivals.preview / .yaml).
export function basisQuery(basis: HandoffBasis): string {
  const q = new URLSearchParams({
    data_frequency: basis.data_frequency,
    demand_unit: basis.demand_unit,
    units_per_order: String(basis.units_per_order),
    operating_hours_per_day: String(basis.operating_hours_per_day),
    operating_days_per_week: String(basis.operating_days_per_week),
  });
  return q.toString();
}

// Plain message for a failed preview or download. Never shows raw HTTP or
// engine errors to the customer.
export function plainError(status: number | null): string {
  if (status === 401 || status === 403) {
    return "Sign in with a Premium plan to send forecasts to SimOS.";
  }
  if (status === 404 || status === 409) {
    return "This forecast run is no longer available. Run it again, then send it to SimOS.";
  }
  if (status === 422) {
    return "The engine could not forecast this series with these settings. Check it has at least 4 numbers, then try again.";
  }
  return "Could not reach the forecast engine. Check your connection and try again.";
}

const PERIOD_WORD: Record<DataFrequency, string> = { day: "day", week: "week", month: "month" };

export function fmtNumber(x: number, digits = 2, fixed = false): string {
  return x.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: fixed ? digits : 0,
  });
}

// The headline the customer confirms: "Period 1: 2,075 units a month becomes
// 2.84 orders an hour in SimOS."
export function headline(preview: HandoffPreview): string {
  const first = preview.steps[0];
  if (!first) return "";
  const what = preview.basis.demand_unit === "units" ? "units" : "orders";
  const per = PERIOD_WORD[preview.basis.data_frequency];
  return (
    `Period 1: ${fmtNumber(first.forecast_median, 0)} ${what} a ${per} becomes ` +
    `${fmtNumber(first.rate_per_hour, 2, true)} orders an hour in SimOS.`
  );
}
