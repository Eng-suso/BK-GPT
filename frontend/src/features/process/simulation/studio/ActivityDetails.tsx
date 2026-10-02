import React from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/ui/button";
import { Meter } from "@/components/data";
import { useReplayFrame } from "../replay/useReplay";
import type { ReplayEngine } from "../replay/replayEngine";
import type { SimulationRun } from "../simulationTypes";
import { useSimulationSection } from "../useSimulationSection";
import { formatDuration } from "../simulationResults";

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
    <h3>{id ? activity?.name ?? engine.payload.elements[id]?.name ?? id : t("simulation.studio.selectActivity")}</h3>
    <p className="sim-help">{t(unavailable ? "simulation.replay.noArtifact" : "simulation.unified.selectionHint")}</p>
    <dl>{[["active", state?.active], ["queued", state?.queued], ["completed", state?.done]].map(([key, value]) => <div key={key}><dt>{t(`simulation.replay.${key}`)}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
    {pool && <div className="sim-activity-resource"><span>{pool}</span>{busy !== undefined && <Meter label={pool} value={Math.round(busy * 100)} tone={busy >= .95 ? "danger" : busy >= .8 ? "warning" : "ok"} />}</div>}
    {activity && <p className="sim-help">{t("simulation.studio.finalWaiting")}: {typeof (activity.wait as { avg?: number })?.avg === "number" ? formatDuration((activity.wait as { avg: number }).avg, i18n.language.startsWith("it") ? "it" : "en") : "\u2014"}</p>}
    <Button size="sm" variant="outline" onClick={() => openPanel?.("scenario")}>{t("simulation.unified.editActivity")}</Button>
  </div>;
}
