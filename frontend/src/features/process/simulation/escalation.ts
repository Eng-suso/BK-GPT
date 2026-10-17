import type { TFunction } from "i18next";

/**
 * SIM-35: dopo quanto scatta un timer d'escalation, in parole: "48 ore",
 * "2 giorni e 4 ore", "30 minuti". Giorni da 24 ore: il timer conta tempo
 * di calendario, non ore lavorative.
 */
export function formatAfter(seconds: number, t: TFunction): string {
  const minutes = Math.round(seconds / 60);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const rest = minutes % 60;
  // 48 ore si legge meglio di 2 giorni: i giorni solo oltre le 72 ore.
  const parts = minutes < 72 * 60
    ? [hours + days * 24 > 0 && t("simulation.duration.hours", { count: hours + days * 24 }), rest > 0 && t("simulation.duration.minutes", { count: rest })]
    : [t("simulation.duration.days", { count: days }), hours > 0 && t("simulation.duration.hours", { count: hours }), rest > 0 && t("simulation.duration.minutes", { count: rest })];
  const words = parts.filter((part): part is string => typeof part === "string");
  return words.length ? words.join(` ${t("simulation.activityInspector.and")} `) : t("simulation.duration.minutes", { count: 0 });
}
