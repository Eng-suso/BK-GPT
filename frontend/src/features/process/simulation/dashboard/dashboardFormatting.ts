import { formatCurrency, formatDuration } from "../simulationResults";
import type { Unit } from "./dashboardModel";

export const WIDGET_COLORS = { blue: "var(--sim-chart-wip)", amber: "var(--sim-chart-queue)", teal: "var(--sim-chart-cost)", violet: "var(--sim-chart-cycle)" };

export function formatMetric(value: number | null, unit: Unit, lang: "it" | "en"): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (unit === "duration") return formatDuration(value, lang);
  if (unit === "currency") return formatCurrency(value, lang);
  const number = new Intl.NumberFormat(lang === "it" ? "it-IT" : "en-US", unit === "rate" ? { maximumSignificantDigits: 3 } : { maximumFractionDigits: 1 }).format(value);
  return unit === "percent" ? `${number}%` : unit === "rate" ? `${number}/h` : number;
}
