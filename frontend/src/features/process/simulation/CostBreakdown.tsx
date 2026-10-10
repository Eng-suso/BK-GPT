import React from "react";
import { useTranslation } from "react-i18next";

import { formatCurrency } from "./simulationResults";
import type { SimulationRun } from "./simulationTypes";

/** SIM-10: da dove viene il costo del run, quando lo scenario ha costi fissi. */
export function CostBreakdown({ run }: { run: SimulationRun }): React.JSX.Element | null {
  const { t, i18n } = useTranslation("process");
  const cost = run.summary?.cost;
  const breakdown = cost?.breakdown;
  if (!cost || !breakdown) return null;
  const lang = i18n.language?.startsWith("it") ? "it" : "en";
  const money = (value: number) => formatCurrency(value, lang);
  return (
    <section aria-label={t("simulation.results.costTitle")} className="mb-3 grid gap-1 rounded-md border border-border p-3" data-sim-cost-breakdown>
      <p className="text-sm font-medium text-foreground">{t("simulation.results.costTitle")}</p>
      <p className="text-sm text-foreground">{t("simulation.results.costTotal", { total: money(cost.total), perCase: money(cost.perCase) })}</p>
      <ul className="grid gap-0.5 text-xs text-muted-foreground">
        <li>{t("simulation.results.costResources", { value: money(breakdown.resources) })}</li>
        {breakdown.activities > 0 && <li>{t("simulation.results.costActivities", { value: money(breakdown.activities) })}</li>}
        {breakdown.cases > 0 && <li>{t("simulation.results.costCases", { value: money(breakdown.cases) })}</li>}
      </ul>
    </section>
  );
}
