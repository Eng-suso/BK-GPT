import React from "react";

import { EmptyState } from "@/components/feedback";
import { Skeleton } from "@/ui/skeleton";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Button } from "@/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/ui/dialog";
import { ROUTES } from "@/app/routes";
import { SimulationBpmnView } from "../SimulationBpmnView";
import { useSimulationSection } from "../useSimulationSection";

import { SimulationConfigRail } from "../SimulationConfigRail";
import { ReadinessSummary } from "../ReadinessSummary";
import { useScenarioLab } from "../useScenarioLab";

/**
 * Scenario builder — the assumptions-review surface. Every simulable element
 * shows where its structure came from (discovery vs. inference) and how far to
 * trust the parameter set for it, rolled up into a Simulation Readiness score.
 */
export function ScenarioBuilderPage(): React.JSX.Element {
  const { t } = useTranslation("process");
  const navigate = useNavigate();
  const { projectId, processId } = useSimulationSection();
  const [reference, setReference] = React.useState<"model" | "readiness" | null>(null);
  const referenceTrigger = React.useRef<HTMLElement | null>(null);
  const pendingField = React.useRef<string | null>(null);
  const openReference = (next: "model" | "readiness") => {
    referenceTrigger.current = document.activeElement as HTMLElement | null;
    setReference(next);
  };
  const lab = useScenarioLab();
  const {
    bpmnXml,
    template,
    templateLoading,
    draft,
    updateDraft,
    provenance,
    confidence,
    isRunning,
    error,
    handleRun,
    activeRun,
  } = lab;

  const [focusEl, setFocusEl] = React.useState<string | null>(null);
  const lowCursor = React.useRef(0);

  const reviewLowest = React.useCallback(() => {
    const ids = confidence.readiness.lowConfidenceElementIds;
    if (ids.length === 0) return;
    const next = ids[lowCursor.current % ids.length];
    lowCursor.current += 1;
    setFocusEl(next);
    pendingField.current = next;
    setReference(null);
  }, [confidence.readiness.lowConfidenceElementIds]);

  if (bpmnXml === null && !templateLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <EmptyState title={t("simulation.diagram.noModel")} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
          <h2 className="text-lg font-semibold tracking-[-0.01em] text-foreground">
            {t("simulation.scenario.pageTitle")}
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {t("simulation.scenario.pageSubtitle")}
          </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => openReference("model")}>{t("simulation.workspace.showModel")}</Button>
            <Button size="sm" variant="outline" onClick={() => openReference("readiness")}>{t("simulation.workspace.assumptions")}</Button>
            {activeRun?.status === "completed" && <Button size="sm" variant="outline" onClick={() => navigate(ROUTES.projects.simulation(projectId, processId, "overview"))}>{t("simulation.workspace.viewResults")}</Button>}
          </div>
        </header>
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-lg border border-border bg-card">
        {templateLoading ? (
          <div className="grid gap-3">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        ) : (
          <SimulationConfigRail
            embedded
            workspace
            template={template}
            templateLoading={templateLoading}
            draft={draft}
            onDraftChange={updateDraft}
            isRunning={isRunning}
            error={error}
            onRun={() => void handleRun()}
            focusElementId={focusEl}
            provenance={confidence}
          />
        )}
      </div>

      <Dialog open={reference !== null} onOpenChange={(open) => { if (!open) setReference(null); }}>
        <DialogContent aria-describedby={undefined} onCloseAutoFocus={(event) => {
          event.preventDefault();
          const field = pendingField.current ? document.querySelector<HTMLElement>(`[data-sim-el="${CSS.escape(pendingField.current)}"] input, [data-sim-el="${CSS.escape(pendingField.current)}"] button`) : null;
          (field ?? referenceTrigger.current)?.focus({ preventScroll: true });
          pendingField.current = null;
        }} className={reference === "model" ? "flex h-[85dvh] flex-col border-border sm:max-w-[calc(100vw-4rem)]" : "max-h-[85dvh] overflow-y-auto border-border sm:max-w-lg"}>
          <DialogTitle>{t(reference === "model" ? "simulation.diagram.title" : "simulation.workspace.assumptions")}</DialogTitle>
          {reference === "model" ? <SimulationBpmnView className="min-h-0 flex-1" bpmnXml={bpmnXml} selectedElementId={focusEl} onSelectElement={(id) => { if (id && (draft.tasks[id] || draft.gateways[id])) { setFocusEl(id); pendingField.current = id; setReference(null); } }} /> :
          <ReadinessSummary
            confidence={confidence}
            provenance={provenance}
            onReview={
              confidence.readiness.lowConfidenceElementIds.length > 0
                ? reviewLowest
                : undefined
            }
          />
          }
        </DialogContent>
      </Dialog>
    </div>
  );
}
