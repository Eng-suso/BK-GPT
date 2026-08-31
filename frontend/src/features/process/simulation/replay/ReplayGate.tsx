import React from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Play, X } from "lucide-react";

import { EmptyState } from "@/components/feedback";

import type { SimulationRun } from "../simulationTypes";
import { resolveActiveRun, useSimulationSection } from "../useSimulationSection";
import { useReplayEngine } from "./useReplay";
import type { ReplayEngine } from "./replayEngine";

type ReplayGateProps = {
  children: (ctx: { engine: ReplayEngine; run: SimulationRun; bpmnXml: string }) => React.ReactNode;
};

/**
 * Resolves the section's active run → a ready {@link ReplayEngine}, rendering the
 * right empty / loading / error state otherwise. Shared by the Replay and
 * Cruscotto screens.
 */
export function ReplayGate({ children }: ReplayGateProps): React.JSX.Element {
  const { t } = useTranslation("process");
  const { runId } = useParams();
  const { runs, bpmnXml } = useSimulationSection();
  const activeRun = resolveActiveRun(runs, runId);

  const { engine, isLoading, noArtifact, error } = useReplayEngine(
    activeRun?.status === "completed" ? activeRun.id : null,
  );

  let body: React.ReactNode;
  if (!activeRun) {
    body = (
      <EmptyState
        icon={Play}
        title={t("simulation.replay.noRun")}
        description={t("simulation.replay.noRunHint")}
      />
    );
  } else if (activeRun.status === "pending") {
    body = <EmptyState icon={Play} title={t("simulation.running")} />;
  } else if (activeRun.status === "failed") {
    body = (
      <EmptyState
        icon={X}
        title={t("simulation.status.failed")}
        description={activeRun.error ?? undefined}
      />
    );
  } else if (isLoading) {
    body = <EmptyState icon={Play} title={t("simulation.loading")} />;
  } else if (noArtifact) {
    body = (
      <EmptyState
        icon={Play}
        title={t("simulation.replay.noArtifact")}
        description={t("simulation.replay.noArtifactHint")}
      />
    );
  } else if (error) {
    body = <EmptyState icon={X} title={error} />;
  } else if (engine && bpmnXml) {
    return <>{children({ engine, run: activeRun, bpmnXml })}</>;
  } else {
    body = <EmptyState icon={Play} title={t("simulation.diagram.noModel")} />;
  }

  return <div className="flex h-full min-h-0 items-center justify-center p-6">{body}</div>;
}
