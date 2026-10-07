import React from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Meter } from "@/components/data";
import { useReplayFrame } from "../replay/useReplay";
import type { ReplayEngine } from "../replay/replayEngine";
import type { SimulationRun } from "../simulationTypes";
import { useSimulationSection } from "../useSimulationSection";
import { formatCurrency, formatDuration } from "../simulationResults";
import { useScenarioProvenance } from "../useInputConfidence";
import { ProvenanceChip } from "../ProvenanceChip";
import { provenanceTip } from "../simulationProvenance";
import { activityParameters, hasTaskConfig } from "./activityParameters";

export function ActivityDetails({ engine, run, unavailable = false }: { engine: ReplayEngine; run: SimulationRun; unavailable?: boolean }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const { selectedElementId, openPanel } = useSimulationSection();
  const frame = useReplayFrame(engine);
  const id = selectedElementId;
  const state = !unavailable && id ? frame?.elements[id] : null;
  const pool = !unavailable && id ? engine.poolForElement(id) : null;
  const busy = pool ? frame?.resources[pool]?.busy : undefined;
  const activity = run.summary?.byActivity?.find((item) => item.el === id);
  return <div className="sim-activity-details">
    <h3>{id ? typeof activity?.name === "string" ? activity.name : engine.payload.elements[id]?.name ?? id : t("simulation.studio.selectActivity")}</h3>
    <p className="sim-help">{t(unavailable ? "simulation.replay.noArtifact" : "simulation.unified.selectionHint")}</p>
    <dl>{[["active", state?.active], ["queued", state?.queued], ["completed", state?.done]].map(([key, value]) => <div key={key}><dt>{t(`simulation.replay.${key}`)}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
    {pool && <div className="sim-activity-resource"><span>{pool}</span>{busy !== undefined && <Meter label={pool} value={Math.round(busy * 100)} tone={busy >= .95 ? "danger" : busy >= .8 ? "warning" : "ok"} />}</div>}
    {activity && <p className="sim-help">{t("simulation.studio.finalWaiting")}: {typeof (activity.wait as { avg?: number })?.avg === "number" ? formatDuration((activity.wait as { avg: number }).avg, i18n.language.startsWith("it") ? "it" : "en") : "—"}</p>}
    {id && <SimulatedParameters run={run} elementId={id} isActivity={Boolean(activity) || hasTaskConfig(run.request, id)} />}
    <Button size="sm" variant="outline" onClick={() => openPanel?.("scenario")}>{t("simulation.unified.editActivity")}</Button>
  </div>;
}

/**
 * SIM-20a: what the run simulated for the selected activity — duration,
 * distribution, resource — and where that value comes from, on the IR's
 * five-level provenance. Confidence is spelled out, not only a coloured dot.
 */
function SimulatedParameters({ run, elementId, isActivity }: { run: SimulationRun; elementId: string; isActivity: boolean }): React.JSX.Element {
  const { t, i18n } = useTranslation("process");
  const lang = i18n.language.startsWith("it") ? "it" : "en";
  const provenance = useScenarioProvenance(run.bpmn_model_id, isActivity);
  const element = provenance.data?.elements.find((el) => el.element_id === elementId && el.kind === "activity");
  const params = isActivity ? activityParameters(run.request, elementId, element) : null;
  const title = t("simulation.activityInspector.title");

  if (!params) {
    return <section className="sim-activity-params" aria-label={title}>
      <h4>{title}</h4>
      <p className="sim-help">{t("simulation.activityInspector.notActivity")}</p>
    </section>;
  }

  const confidence = t(`simulation.provenance.confidence.${params.provenance.confidence}`);
  return <section className="sim-activity-params" aria-label={title}>
    <h4>{title}</h4>
    <dl>
      <div><dt>{t("simulation.activityInspector.duration")}</dt><dd>{formatDuration(params.meanSeconds, lang)}{params.usesDefault && <span className="sim-param-note">{t("simulation.activityInspector.defaultDuration")}</span>}</dd></div>
      <div><dt>{t("simulation.activityInspector.distribution")}</dt><dd>{t(`simulation.config.dist.${params.distribution}`)}{params.stdShareOfMean != null && <span className="sim-param-note">{t("simulation.activityInspector.normalStd", { pct: Math.round(params.stdShareOfMean * 100) })}</span>}</dd></div>
      {params.resource && <div><dt>{t("simulation.activityInspector.resource")}</dt><dd>{t("simulation.activityInspector.resourceValue", { name: params.resource.name, amount: params.resource.amount, cost: formatCurrency(params.resource.costPerHour, lang) })}</dd></div>}
      <div><dt>{t("simulation.activityInspector.origin")}</dt><dd>
        {provenance.isLoading && !provenance.data
          ? <span className="sim-param-note" role="status">{t("simulation.activityInspector.provenanceLoading")}</span>
          : <><ProvenanceChip field={params.provenance} hideNote /><span className="sim-param-note">{t("simulation.activityInspector.confidence", { level: confidence })}</span></>}
      </dd></div>
    </dl>
    {provenance.isError && !provenance.data
      ? <p className="sim-help" role="alert">{t("simulation.activityInspector.provenanceError")}</p>
      : !provenance.isLoading && <p className="sim-help">{provenanceTip(params.provenance, t)}</p>}
  </section>;
}
