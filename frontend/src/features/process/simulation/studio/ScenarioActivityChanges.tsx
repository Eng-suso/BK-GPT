import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Button } from "@/ui/button";

import { fetchScenarioTemplate } from "../simulationApi";
import { parseScenarioDraft, seedDraftFromTemplate } from "../simulationScenario";
import { fetchScenarioWorkspace, scenarioDisplayName, type ScenarioWorkspace } from "../scenarioWorkspace";
import type { ScenarioTemplate } from "../simulationTypes";
import { useScenarioChanges } from "../useScenarioChanges";
import { useSimulationSection } from "../useSimulationSection";

/**
 * SIM-14 nell'inspector del task: come gli scenari del workspace cambiano
 * questa attivita' o decisione rispetto all'AS-IS. Niente se nessuno la tocca.
 */
export function ScenarioActivityChanges({ elementId }: { elementId: string }): React.JSX.Element | null {
  const { t } = useTranslation("process");
  const { process } = useSimulationSection();
  const bpmnModelId = process.bpmnModelId;
  const [params, setParams] = useSearchParams();
  // Le stesse chiavi del pannello Scenario: i dati arrivano dalla cache.
  const workspace = useQuery<ScenarioWorkspace>({
    queryKey: ["workspace", "simulation-scenarios", bpmnModelId],
    queryFn: () => fetchScenarioWorkspace(bpmnModelId),
    staleTime: 30_000,
  });
  const template = useQuery<ScenarioTemplate>({
    queryKey: ["workspace", "simulation-template", bpmnModelId],
    queryFn: () => fetchScenarioTemplate(bpmnModelId, null),
    staleTime: 60_000,
  });
  const baseline = React.useMemo(() => {
    const draft = workspace.data?.baseline?.draft;
    if (!draft) return null;
    const parsed = parseScenarioDraft(draft);
    return template.data ? seedDraftFromTemplate(parsed, template.data) : parsed;
  }, [workspace.data, template.data]);
  const changes = useScenarioChanges(baseline, template.data ?? null);

  const rows = (workspace.data?.alternatives ?? []).flatMap((scenario) =>
    changes.read(scenario).filter((change) => change.elementId === elementId).map((change) => ({ scenario, change })));
  if (!rows.length) return null;
  const title = t("simulation.scenarios.inspector.title");
  const edit = (id: number) => {
    const next = new URLSearchParams(params);
    next.set("scenario", String(id));
    next.set("panel", "scenario");
    setParams(next);
  };
  return (
    <section className="sim-real-activity" aria-label={title} data-sim-scenario-activity>
      <h4>{title}</h4>
      <ul className="grid gap-1.5">
        {rows.map(({ scenario, change }) => (
          <li key={`${scenario.id}-${change.index}`} className="flex items-start justify-between gap-2 text-xs">
            <span className="min-w-0 text-foreground">
              {t("simulation.scenarios.inspector.change", { scenario: scenarioDisplayName(scenario), what: changes.text(change) })}
              {change.conflict && <small className="block text-[var(--state-warning-text)]">{t("simulation.scenarios.conflictOp")}</small>}
            </span>
            <Button size="sm" variant="ghost" aria-label={t("simulation.scenarios.workspace.editScenario", { name: scenarioDisplayName(scenario) })} onClick={() => edit(scenario.id)}>
              {t("simulation.scenarios.workspace.edit")}
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
