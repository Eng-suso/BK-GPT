import React from "react";
import { useTranslation } from "react-i18next";

import { formatCurrency } from "./simulationResults";
import type { SimulationRun } from "./simulationTypes";

/** SIM-03: i KPI escludono i primi casi, che hanno trovato il sistema vuoto. */
export function WarmupNote({ run }: { run: SimulationRun }): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const warmup = run.summary?.warmup;
  if (!warmup) return null;
  return (
    <p className="mb-3 text-xs text-muted-foreground" data-sim-warmup-note>
      {t("simulation.results.warmupNote", { excluded: warmup.excludedCases, measured: warmup.measuredCases })}
    </p>
  );
}

/** SIM-03: il run ha simulato un periodo; i KPI misurano i casi completati, gli altri restano aperti. */
export function HorizonNote({ run }: { run: SimulationRun }): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const horizon = run.summary?.horizon;
  if (!horizon) return null;
  return (
    <div className="mb-3 grid gap-1" data-sim-horizon-note>
      <p className="text-xs text-muted-foreground">
        {t("simulation.results.horizonNote", {
          count: horizon.days, completed: horizon.completedCases, open: horizon.openCases, arrived: horizon.arrivedCases,
        })}
      </p>
      {!horizon.covered && <p role="status" className="text-xs font-medium text-warning">{t("simulation.results.horizonUncovered")}</p>}
    </div>
  );
}

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
