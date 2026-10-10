import React from "react";
import { useTranslation } from "react-i18next";

import { describeChanges, type ChangeNames, type ScenarioChange } from "./scenarioChanges";
import type { WorkspaceScenario } from "./scenarioWorkspace";
import type { ScenarioDraft } from "./simulationScenario";
import type { ScenarioTemplate } from "./simulationTypes";

/**
 * SIM-14: legge la patch di uno scenario con i nomi del processo (attivita',
 * decisioni, rami, risorse) e le etichette tradotte del pannello.
 */
export function useScenarioChanges(baseline: ScenarioDraft | null, template: ScenarioTemplate | null) {
  const { t, i18n } = useTranslation("process");
  const locale = i18n.language?.startsWith("it") ? "it-IT" : "en-US";
  const names = React.useMemo<ChangeNames>(() => {
    const elements: Record<string, string> = {};
    for (const task of template?.tasks ?? []) elements[task.element_id] = task.name || task.element_id;
    for (const gateway of template?.gateways ?? []) {
      elements[gateway.element_id] = gateway.name || gateway.element_id;
      for (const branch of gateway.branches) {
        elements[branch.flow_id] = t("simulation.scenarios.branchTo", { target: branch.target_name || branch.flow_name || branch.flow_id });
      }
    }
    const resources = Object.fromEntries((baseline?.resources ?? []).map((r) => [r.id, r.name || r.id]));
    return { elements, resources };
  }, [template, baseline, t]);

  const read = React.useCallback((scenario: WorkspaceScenario): ScenarioChange[] => describeChanges(
    scenario.patch,
    scenario.conflicts,
    baseline ?? {},
    names,
    {
      field: (key) => t(`simulation.scenarios.field.${key}`, { defaultValue: key }),
      section: (key) => t(`simulation.scenarios.section.${key}`, { defaultValue: key }),
      number: (value) => value.toLocaleString(locale, { maximumFractionDigits: 2 }),
      complex: t("simulation.scenarios.complex"),
      text: (key, value) => {
        if (key === "distribution") return t(`simulation.config.dist.${value}`, { defaultValue: value });
        if (key === "unit") return t(value === "hours" ? "simulation.config.slaHours" : "simulation.config.slaDays");
        return value;
      },
      yes: t("simulation.scenarios.yes"),
      no: t("simulation.scenarios.no"),
    },
  ), [baseline, names, t, locale]);

  /** Una riga leggibile: "Approvatore · Unita': 1 → 2", "Bot: aggiunto". */
  const text = React.useCallback((change: ScenarioChange): string => {
    const what = change.field ? `${change.subject} · ${change.field}` : change.subject;
    if (change.kind === "removed" || change.kind === "reordered") return `${what}: ${t(`simulation.scenarios.kind.${change.kind}`)}`;
    if (change.kind === "added") return change.to ? `${what}: ${change.to} (${t("simulation.scenarios.kind.added")})` : `${what}: ${t("simulation.scenarios.kind.added")}`;
    return `${what}: ${change.from ?? "—"} → ${change.to ?? "—"}`;
  }, [t]);

  return { read, text };
}
